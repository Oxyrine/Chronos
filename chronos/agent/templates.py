"""Small deterministic patch vocabulary. Model output is data, never commands."""
import difflib
import re

T1 = "T1_nginx_hybrid_groups"
T2 = "T2_sshd_hybrid_kex"
T3 = "T3_client_tls_groups"
HYBRID = "X25519MLKEM768"
KEX = ["mlkem768x25519-sha256", "sntrup761x25519-sha512@openssh.com", "curve25519-sha256"]


def parameters(template_id: str, mode: str = "compatibility") -> dict:
    if mode not in ("compatibility", "strict"):
        raise ValueError("mode must be compatibility or strict")
    if template_id == T1:
        return {"groups": [HYBRID] if mode == "strict" else [HYBRID, "X25519", "prime256v1"],
                "protocols": ["TLSv1.3"] if mode == "strict" else ["TLSv1.3", "TLSv1.2"]}
    if mode == "strict":
        raise ValueError("strict mode is available only for T1")
    if template_id == T2:
        return {"kex": list(KEX)}
    if template_id == T3:
        return {"groups": [HYBRID, "X25519"]}
    raise ValueError("template is not enabled")


def check_parameters(template_id: str, params: dict) -> None:
    allowed = [parameters(template_id)]
    if template_id == T1:
        allowed.append(parameters(T1, "strict"))
    if params not in allowed:
        raise ValueError("parameters must exactly match an allowed template variant")


def _replace_once(text: str, pattern: str, directive: str) -> str:
    rx = re.compile(pattern, re.MULTILINE | re.IGNORECASE)
    matches = list(rx.finditer(text))
    if len(matches) != 1:
        raise ValueError("target must contain exactly one " + directive.split()[0] + " directive")
    return rx.sub(lambda m: m.group("indent") + directive, text)


def render(template_id: str, params: dict, original: str, target: str) -> tuple[str, str]:
    check_parameters(template_id, params)
    newline = "\r\n" if "\r\n" in original else "\n"
    text = original.replace("\r\n", "\n")
    if template_id == T1:
        text = _replace_once(text, r"^(?P<indent>[ \t]*)ssl_protocols\s+[^;\r\n]+;[ \t]*(?:#[^\r\n]*)?$",
                             "ssl_protocols " + " ".join(params["protocols"]) + ";")
        text = _replace_once(text, r"^(?P<indent>[ \t]*)ssl_ecdh_curve\s+[^;\r\n]+;[ \t]*(?:#[^\r\n]*)?$",
                             "ssl_ecdh_curve " + ":".join(params["groups"]) + ";")
    elif template_id == T2:
        if re.search(r"^\s*Match\s", text, re.MULTILINE | re.IGNORECASE):
            raise ValueError("sshd Match blocks require manual review")
        text = _replace_once(text, r"^(?P<indent>[ \t]*)KexAlgorithms\s+[^\r\n]+$",
                             "KexAlgorithms " + ",".join(params["kex"]))
    elif template_id == T3:
        text = _replace_once(text, r"^(?P<indent>[ \t]*)Groups\s*=\s*[^\r\n]+$",
                             "Groups = " + ":".join(params["groups"]))
    if not text.endswith("\n"):
        text += "\n"
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    diff = "".join(difflib.unified_diff(original.splitlines(keepends=True), text.splitlines(keepends=True),
                                         fromfile="a/" + target, tofile="b/" + target))
    if not diff:
        raise ValueError("proposal makes no change")
    return text, diff


def catalog() -> list[dict]:
    return [{"template_id": t, "allowed_params": [parameters(t)] + ([parameters(t, "strict")] if t == T1 else [])}
            for t in (T1, T2, T3)]
