"""공통 로그 유틸리티 — cp949 환경에서도 안전한 출력"""


def safe_log(prefix: str, msg: str) -> None:
    """Windows cp949 환경에서도 안전하게 로그 출력"""
    try:
        print(f"[{prefix}] {msg}")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            safe_msg = msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(f"[{prefix}] {safe_msg}")
        except Exception:
            pass
