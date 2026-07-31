"""تطبيع أسماء مساحات العمل — حقل يُكتب حراً في الواجهة فيحتاج تحصيناً قبل التخزين."""
import re

_WS_CLEAN = re.compile(r"[\\/\r\n\t]+")


def sanitize_workspace_name(name: str) -> str:
    """تنظيف اسم مساحة العمل: بلا فواصل مسارات، بطول معقول، والافتراضي Default."""
    name = _WS_CLEAN.sub("-", (name or "").strip())
    name = re.sub(r"\s{2,}", " ", name)
    return name[:40] or "Default"
