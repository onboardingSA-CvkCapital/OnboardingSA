"""advert_sections.py  -  OnboardingSA

Split a company job advert (HTML) into: about the role / duties / requirements, using the advert's own headings.
Shared by the company scrapers (Workday sites, Heineken). Fixed rules, no AI.
"""
import re, html

H_ABOUT = re.compile(r"^((main )?purpose of the (job|role|position)|job purpose|role purpose|purpose|about the role|"
                     r"about the job|about the position|about the program(me)?|job summary|role summary|position summary|overview|"
                     r"the role|your role|what is the role|introduction|job description|description)\b", re.I)
H_RESP = re.compile(r"^(key roles?( &| and)? responsibilities|roles? and responsibilities|key responsibilities|"
                    r"responsibilities|your responsibilities|duties|main duties|key duties|key performance areas|kpas?|"
                    r"key result areas|required outputs?|what you will learn|what you'll learn|outputs|job profile|what you will do|what you'll do|"
                    r"what will you do|your main tasks|the job|key accountabilities|accountabilities|job functions)\b", re.I)
H_REQ = re.compile(r"^(requirements|minimum requirements|job requirements|qualifications?|education|experience|"
                   r"knowledge|skills|key competencies|competencies|personal attributes|behavioural|technical skills|"
                   r"what you need|what you will need|what you'll need|what we are looking for|what we're looking for|"
                   r"the (successful|ideal) candidate|we'?re looking for|we are looking for|who are we looking for|who you are|your profile|profile|candidate profile|about you|you have|must have|nice to have|"
                   r"advantageous|preferred|conditions of employment)\b", re.I)
H_STOP = re.compile(r"^(application process|candidates who do not receive|additional information|what we offer|we offer|what's in it for you|benefits|our offer|about us|about the company|"
                    r"who we are|why join|equal opportunit|employment equity|disclaimer|please note|note:|"
                    r"if you do not hear|only shortlisted|closing date|how to apply|privacy|discover who we are|"
                    r"summary$|.* respects your right to privacy|.* is an equal opportunity)", re.I)


def lines_of(desc):
    """Advert HTML -> [(text, is_bold)], one entry per visual line."""
    d = re.sub(r"<(strong|b)\b[^>]*>", "\x01", desc or "", flags=re.I)
    d = re.sub(r"</(strong|b)>", "\x02", d, flags=re.I)
    d = re.sub(r"<br\s*/?>|</p>|</li>|</div>|</h\d>|<li\b[^>]*>|<p\b[^>]*>|<h\d\b[^>]*>", "\n", d, flags=re.I)
    d = html.unescape(re.sub(r"<[^>]+>", "", d)).replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    out = []
    for raw in d.split("\n"):
        t = raw.strip()
        if not t.replace("\x01", "").replace("\x02", "").strip():
            continue
        inner = t[1:-1] if len(t) > 1 else ""
        bold = t.startswith("\x01") and t.endswith("\x02") and not re.search(r"\x02\s*[^\s\x01]", inner)
        t = re.sub(r"\s+", " ", t.replace("\x01", "").replace("\x02", "")).strip()
        t = re.sub(r"^(?:[•·▪◦●\-–*]|\d{1,2}[.)])\s*", "", t).strip()
        if t:
            out.append((t, bold))
    return out


def sections(desc, skip=None):
    """Return (about, duties, requirements) as lists of lines. `skip` is an optional regex of company boilerplate lines."""
    about, resp, req, pre, body, sec = [], [], [], [], [], None
    for t, bold in lines_of(desc):
        head = t.rstrip(":.").strip()
        short = len(head) <= 90
        looks_head = short and (bold or t.endswith(":") or (head.isupper() and len(head) > 3))
        if short and H_STOP.match(head):
            sec = "stop"
            continue
        known = short and len(head.split()) <= 7 and not head.endswith(".") and (
            H_ABOUT.match(head) or H_RESP.match(head) or H_REQ.match(head))
        if looks_head or known:
            if H_RESP.match(head):
                sec = "resp"
            elif H_REQ.match(head):
                if sec == "req" or not re.match(r"^(minimum |job )?requirements$|^qualifications?( and experience)?$", head, re.I):
                    req.append((head.capitalize() if head.isupper() else head) + ":")
                sec = "req"
            elif H_ABOUT.match(head):
                sec = "about"
            elif sec in ("resp", "req") and looks_head:
                (resp if sec == "resp" else req).append((head.capitalize() if head.isupper() else head) + ":")
            elif looks_head and sec is None:
                pass                                   # company slogan / intro heading
            continue
        if skip is not None and skip.search(t):
            continue
        if sec != "stop":
            body.append(t)
        if sec is None and len(t) > 60:
            pre.append(t)                              # text before the first heading: usually the role summary
        elif sec == "about":
            about.append(t)
        elif sec == "resp":
            resp.append(t)
        elif sec == "req":
            req.append(t)
    for lst in (resp, req):
        while lst and lst[-1].endswith(":"):
            lst.pop()
    if not resp and not req:
        return body, resp, req                         # no headings we know: keep the whole advert text as written
    return (about or pre[-2:]), resp, req


def usable(about, resp, req):
    """Enough real content to publish: duties or requirements, or a full advert text of 60+ words."""
    return bool(resp or req) or len(" ".join(about).split()) >= 60
