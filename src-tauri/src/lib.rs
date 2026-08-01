use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, State};

// Fixed local port for the bundled FastAPI backend. Simple and good enough
// for a single-instance desktop app; a stray leftover process holding this
// port is the one scenario that surfaces as a startup error to the user.
const BACKEND_PORT: u16 = 47861;
const READY_TIMEOUT_SECS: u64 = 90; // first run can be slower (EasyOCR model download)

struct BackendProcess(Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            spawn_backend(app.handle())?;

            let handle = app.handle().clone();
            std::thread::spawn(move || wait_for_backend_then_show(handle));

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                stop_backend(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

/// Finds the bundled backend/LibreOffice under `resource_dir` first (installed
/// app), then falls back to `dist/waraq-backend` next to the project during
/// `cargo tauri dev` on this machine so the whole flow can be smoke-tested
/// without a full installer build.
fn locate(resource_dir: &Path, dev_fallback: &Path, candidates: &[&str]) -> Option<PathBuf> {
    for base in [resource_dir, dev_fallback] {
        for rel in candidates {
            let path = base.join(rel);
            if path.exists() {
                return Some(path);
            }
        }
    }
    None
}

fn spawn_backend(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let resource_dir = app.path().resource_dir()?;
    let data_dir = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;

    // Only used for local `cargo tauri dev` iteration on this machine — the
    // installed app always resolves everything under resource_dir.
    let project_root = resource_dir
        .parent()
        .and_then(|p| p.parent())
        .map(PathBuf::from)
        .unwrap_or_else(|| resource_dir.clone());

    let backend_exe = locate(
        &resource_dir,
        &project_root,
        &[
            "backend/waraq-backend/waraq-backend.exe",
            "backend/waraq-backend/waraq-backend",
            "dist/waraq-backend/waraq-backend.exe",
            "dist/waraq-backend/waraq-backend",
        ],
    )
    .ok_or("backend executable not found in app resources")?;

    let soffice = locate(
        &resource_dir,
        &project_root,
        &["libreoffice/program/soffice.exe", "libreoffice/program/soffice"],
    );

    // Piped stdio that nobody reads is a deadlock waiting to happen: once the OS
    // pipe buffer fills (uvicorn's access log alone gets there over time), the
    // child blocks on its next write and the whole backend freezes — surfacing
    // to the user as "can't connect to the server" long after it looked fine.
    // Writing straight to a file has no such buffer limit, and doubles as a real
    // log to diagnose issues from instead of guessing.
    let log_path = data_dir.join("backend.log");
    let stdout_log = std::fs::File::create(&log_path)?;
    let stderr_log = stdout_log.try_clone()?;

    let mut cmd = Command::new(&backend_exe);
    cmd.env("WARAQ_PORT", BACKEND_PORT.to_string())
        .env("WARAQ_DATA_DIR", &data_dir)
        .stdout(Stdio::from(stdout_log))
        .stderr(Stdio::from(stderr_log));

    if let Some(soffice_path) = soffice {
        cmd.env("SOFFICE_PATH", soffice_path);
        cmd.env("PDF_ENGINE", "libreoffice");
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let child = cmd.spawn().map_err(|e| format!("failed to start backend: {e}"))?;

    let state: State<BackendProcess> = app.state();
    *state.0.lock().unwrap() = Some(child);
    Ok(())
}

fn stop_backend(app: &tauri::AppHandle) {
    let state: State<BackendProcess> = app.state();
    let child = state.0.lock().unwrap().take();
    if let Some(mut child) = child {
        let _ = child.kill();
        let _ = child.wait();
    }
}

const OCR_POLL_FAILURE_TIMEOUT_SECS: u64 = 60; // backend must answer again within this or it's dead
const OCR_ABSOLUTE_TIMEOUT_SECS: u64 = 1800;   // 30 min hard cap regardless of activity

fn escape_js_string(s: &str) -> String {
    serde_json::to_string(s).unwrap_or_else(|_| "\"\"".to_string())
}

fn splash_show_error(window: &tauri::WebviewWindow, message: &str) {
    let js = format!(
        "window.waraqSetError && window.waraqSetError({});",
        escape_js_string(message)
    );
    let _ = window.eval(&js);
}

fn splash_update_progress(window: &tauri::WebviewWindow, info: &serde_json::Value) {
    let phase = info.get("phase").and_then(|v| v.as_str()).unwrap_or("");
    let percent = info.get("percent").and_then(|v| v.as_f64());
    let stage = info.get("message").and_then(|v| v.as_str()).unwrap_or("");
    let js = format!(
        "window.waraqSetProgress && window.waraqSetProgress({}, {}, {});",
        escape_js_string(phase),
        percent.map(|p| p.to_string()).unwrap_or_else(|| "null".to_string()),
        escape_js_string(stage),
    );
    let _ = window.eval(&js);
}

/// Polls the backend's own health endpoint (blocking, on a plain thread —
/// simpler than pulling in async plumbing for one readiness loop), then keeps
/// polling OCR setup progress and reflecting it on the splash screen until the
/// engine is actually ready — only then does it navigate to the real app, so
/// the user never lands on a UI that silently can't process documents yet.
fn wait_for_backend_then_show(app: tauri::AppHandle) {
    let status_url = format!("http://127.0.0.1:{BACKEND_PORT}/status");
    let progress_url = format!("http://127.0.0.1:{BACKEND_PORT}/ocr/progress");

    let deadline = Instant::now() + Duration::from_secs(READY_TIMEOUT_SECS);
    let server_up = loop {
        if let Ok(resp) = ureq::get(&status_url).timeout(Duration::from_secs(2)).call() {
            if resp.status() == 200 {
                break true;
            }
        }
        if Instant::now() >= deadline {
            break false;
        }
        std::thread::sleep(Duration::from_millis(400));
    };

    let Some(window) = app.get_webview_window("main") else { return };

    if !server_up {
        splash_show_error(
            &window,
            "تعذّر تشغيل الخادم المحلي. أغلق التطبيق وأعد فتحه، وتأكد من عدم وجود نسخة أخرى قيد التشغيل.",
        );
        return;
    }

    let start = Instant::now();
    let mut last_ok_at = Instant::now();
    let ocr_ready = loop {
        match ureq::get(&progress_url).timeout(Duration::from_secs(5)).call() {
            Ok(resp) if resp.status() == 200 => {
                last_ok_at = Instant::now();
                if let Ok(body) = resp.into_string() {
                    if let Ok(info) = serde_json::from_str::<serde_json::Value>(&body) {
                        let phase = info.get("phase").and_then(|v| v.as_str()).unwrap_or("");
                        if phase == "ready" {
                            break true;
                        }
                        if phase == "error" {
                            let msg = info.get("message").and_then(|v| v.as_str()).unwrap_or("");
                            splash_show_error(&window, &format!("تعذّر تجهيز محرك OCR: {msg}"));
                            return;
                        }
                        splash_update_progress(&window, &info);
                    }
                }
            }
            _ => {}
        }
        let now = Instant::now();
        if now.duration_since(last_ok_at) >= Duration::from_secs(OCR_POLL_FAILURE_TIMEOUT_SECS)
            || now.duration_since(start) >= Duration::from_secs(OCR_ABSOLUTE_TIMEOUT_SECS)
        {
            break false;
        }
        std::thread::sleep(Duration::from_millis(500));
    };

    if !ocr_ready {
        splash_show_error(
            &window,
            "تعذّر تشغيل الخادم المحلي. أغلق التطبيق وأعد فتحه، وتأكد من عدم وجود نسخة أخرى قيد التشغيل.",
        );
        return;
    }

    if let Ok(url) = url::Url::parse(&format!("http://127.0.0.1:{BACKEND_PORT}/")) {
        let _ = window.navigate(url);
    }
}
