"""Levi Monster — configuration, canon map, curated context channels."""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("LEVI_DATA_DIR", ROOT / "data"))
SRC_DIR = Path(os.environ.get("LEVI_SRC_DIR", DATA_DIR / "src"))
DB_DIR = Path(os.environ.get("LEVI_DB_DIR", DATA_DIR / "db"))
DB_PATH = Path(os.environ.get("LEVI_DB_PATH", DB_DIR / "levi.db"))
CACHE_DIR = Path(os.environ.get("LEVI_CACHE_DIR", DATA_DIR / "cache"))
_default_studies = ROOT / "data" / "studies"
if not _default_studies.exists():
    _default_studies = ROOT / "studies"
STUDIES_DIR = Path(os.environ.get("LEVI_STUDIES_DIR", str(_default_studies)))

# Local user registry.  The JSON file is the table; notebooks are Markdown.
USERS_PATH = Path(os.environ.get("LEVI_USERS_PATH", DATA_DIR / "users.json"))
USER_DIR = Path(os.environ.get("LEVI_USER_DIR", DATA_DIR / "users"))
DEFAULT_USER_ID = os.environ.get("LEVI_DEFAULT_USER", "damian")

# ── Canon ────────────────────────────────────────────────────────────
# full, short OSIS, KJV-db name, STEPBible code, testament, chapters
_BOOK_ROWS = [
    ("Genesis", "Gen", "Genesis", "Gen", "OT", 50),
    ("Exodus", "Exod", "Exodus", "Exo", "OT", 40),
    ("Leviticus", "Lev", "Leviticus", "Lev", "OT", 27),
    ("Numbers", "Num", "Numbers", "Num", "OT", 36),
    ("Deuteronomy", "Deut", "Deuteronomy", "Deu", "OT", 34),
    ("Joshua", "Josh", "Joshua", "Jos", "OT", 24),
    ("Judges", "Judg", "Judges", "Jdg", "OT", 21),
    ("Ruth", "Ruth", "Ruth", "Rut", "OT", 4),
    ("1Samuel", "1Sam", "I Samuel", "1Sa", "OT", 31),
    ("2Samuel", "2Sam", "II Samuel", "2Sa", "OT", 24),
    ("1Kings", "1Kgs", "I Kings", "1Ki", "OT", 22),
    ("2Kings", "2Kgs", "II Kings", "2Ki", "OT", 25),
    ("1Chronicles", "1Chr", "I Chronicles", "1Ch", "OT", 29),
    ("2Chronicles", "2Chr", "II Chronicles", "2Ch", "OT", 36),
    ("Ezra", "Ezra", "Ezra", "Ezr", "OT", 10),
    ("Nehemiah", "Neh", "Nehemiah", "Neh", "OT", 13),
    ("Esther", "Esth", "Esther", "Est", "OT", 10),
    ("Job", "Job", "Job", "Job", "OT", 42),
    ("Psalms", "Ps", "Psalms", "Psa", "OT", 150),
    ("Proverbs", "Prov", "Proverbs", "Pro", "OT", 31),
    ("Ecclesiastes", "Eccl", "Ecclesiastes", "Ecc", "OT", 12),
    ("SongofSolomon", "Song", "Song of Solomon", "Sng", "OT", 8),
    ("Isaiah", "Isa", "Isaiah", "Isa", "OT", 66),
    ("Jeremiah", "Jer", "Jeremiah", "Jer", "OT", 52),
    ("Lamentations", "Lam", "Lamentations", "Lam", "OT", 5),
    ("Ezekiel", "Ezek", "Ezekiel", "Ezk", "OT", 48),
    ("Daniel", "Dan", "Daniel", "Dan", "OT", 12),
    ("Hosea", "Hos", "Hosea", "Hos", "OT", 14),
    ("Joel", "Joel", "Joel", "Jol", "OT", 3),
    ("Amos", "Amos", "Amos", "Amo", "OT", 9),
    ("Obadiah", "Obad", "Obadiah", "Oba", "OT", 1),
    ("Jonah", "Jonah", "Jonah", "Jon", "OT", 4),
    ("Micah", "Mic", "Micah", "Mic", "OT", 7),
    ("Nahum", "Nah", "Nahum", "Nah", "OT", 3),
    ("Habakkuk", "Hab", "Habakkuk", "Hab", "OT", 3),
    ("Zephaniah", "Zeph", "Zephaniah", "Zep", "OT", 3),
    ("Haggai", "Hag", "Haggai", "Hag", "OT", 2),
    ("Zechariah", "Zech", "Zechariah", "Zec", "OT", 14),
    ("Malachi", "Mal", "Malachi", "Mal", "OT", 4),
    ("Matthew", "Matt", "Matthew", "Mat", "NT", 28),
    ("Mark", "Mark", "Mark", "Mar", "NT", 16),
    ("Luke", "Luke", "Luke", "Luk", "NT", 24),
    ("John", "John", "John", "Jhn", "NT", 21),
    ("Acts", "Acts", "Acts", "Act", "NT", 28),
    ("Romans", "Rom", "Romans", "Rom", "NT", 16),
    ("1Corinthians", "1Cor", "I Corinthians", "1Co", "NT", 16),
    ("2Corinthians", "2Cor", "II Corinthians", "2Co", "NT", 13),
    ("Galatians", "Gal", "Galatians", "Gal", "NT", 6),
    ("Ephesians", "Eph", "Ephesians", "Eph", "NT", 6),
    ("Philippians", "Phil", "Philippians", "Php", "NT", 4),
    ("Colossians", "Col", "Colossians", "Col", "NT", 4),
    ("1Thessalonians", "1Thess", "I Thessalonians", "1Th", "NT", 5),
    ("2Thessalonians", "2Thess", "II Thessalonians", "2Th", "NT", 3),
    ("1Timothy", "1Tim", "I Timothy", "1Ti", "NT", 6),
    ("2Timothy", "2Tim", "II Timothy", "2Ti", "NT", 4),
    ("Titus", "Titus", "Titus", "Tit", "NT", 3),
    ("Philemon", "Phlm", "Philemon", "Phm", "NT", 1),
    ("Hebrews", "Heb", "Hebrews", "Heb", "NT", 13),
    ("James", "Jas", "James", "Jas", "NT", 5),
    ("1Peter", "1Pet", "I Peter", "1Pe", "NT", 5),
    ("2Peter", "2Pet", "II Peter", "2Pe", "NT", 3),
    ("1John", "1John", "I John", "1Jn", "NT", 5),
    ("2John", "2John", "II John", "2Jn", "NT", 1),
    ("3John", "3John", "III John", "3Jn", "NT", 1),
    ("Jude", "Jude", "Jude", "Jud", "NT", 1),
    ("Revelation", "Rev", "Revelation of John", "Rev", "NT", 22),
]

BOOKS = [
    {"full": f, "short": s, "kjv": k, "step": st, "testament": t, "chapters": c}
    for f, s, k, st, t, c in _BOOK_ROWS
]
BOOK_BY_FULL = {b["full"]: b for b in BOOKS}
BOOK_ORDER = {b["full"]: i for i, b in enumerate(BOOKS, 1)}
CHAPTER_COUNTS = {b["full"]: b["chapters"] for b in BOOKS}

def _norm_key(x: str) -> str:
    x = unicodedata.normalize("NFKD", x)
    x = "".join(c for c in x if not unicodedata.combining(c))
    return re.sub(r"[\s._\-]+", "", x).lower()

_ALIASES = {}
for b in BOOKS:
    for key in (b["full"], b["short"], b["kjv"], b["step"]):
        _ALIASES[_norm_key(key)] = b["full"]
# common alternate spellings / abbreviations
_EXTRA = {
    "psalm": "Psalms", "psa": "Psalms", "psm": "Psalms", "songofsongs": "SongofSolomon",
    "canticles": "SongofSolomon", "sos": "SongofSolomon", "qoheleth": "Ecclesiastes",
    "ecclesiasticus": "Ecclesiastes", "1samuel": "1Samuel", "2samuel": "2Samuel",
    "1kings": "1Kings", "2kings": "2Kings", "1chronicles": "1Chronicles",
    "2chronicles": "2Chronicles", "1cor": "1Corinthians", "2cor": "2Corinthians",
    "1thess": "1Thessalonians", "2thess": "2Thessalonians", "1tim": "1Timothy",
    "2tim": "2Timothy", "1pet": "1Peter", "2pet": "2Peter", "1jn": "1John",
    "2jn": "2John", "3jn": "3John", "philem": "Philemon", "philm": "Philemon",
    "rev": "Revelation", "apocalypse": "Revelation", "jn": "John", "mt": "Matthew",
    "mk": "Mark", "lk": "Luke", "rom": "Romans", "gal": "Galatians",
    "eph": "Ephesians", "phil": "Philippians", "col": "Colossians",
    "heb": "Hebrews", "jas": "James", "jud": "Jude", "dan": "Daniel",
    "ezek": "Ezekiel", "eccl": "Ecclesiastes", "deut": "Deuteronomy",
    "josh": "Joshua", "judg": "Judges", "prov": "Proverbs", "isa": "Isaiah",
    "jer": "Jeremiah", "lam": "Lamentations", "obad": "Obadiah", "mic": "Micah",
    "nah": "Nahum", "hab": "Habakkuk", "zeph": "Zephaniah", "hag": "Haggai",
    "zech": "Zechariah", "mal": "Malachi", "matt": "Matthew",
}
_ALIASES.update({_norm_key(k): v for k, v in _EXTRA.items()})

def resolve_book(name: str) -> str | None:
    """Resolve any book spelling/abbreviation to canonical full name."""
    if not name:
        return None
    key = _norm_key(name)
    if key in _ALIASES:
        return _ALIASES[key]
    # "I John" -> "1John"
    roman = {"i": "1", "ii": "2", "iii": "3"}
    m = re.match(r"^(i{1,3})\s*(.+)$", name.strip(), re.I)
    if m:
        alt = roman[m.group(1).lower()] + _norm_key(m.group(2))
        if alt in _ALIASES:
            return _ALIASES[alt]
    # prefix match on full names
    for b in BOOKS:
        if _norm_key(b["full"]).startswith(key) and len(key) >= 3:
            return b["full"]
    return None

def verse_id(book: str, chapter: int, verse: int) -> str:
    return f"{book}.{chapter}.{verse}"

def parse_ref(ref: str) -> dict | None:
    """Parse 'John 3:16', 'Jn 3.16', '1 Cor 13:4-7', 'Genesis 1'."""
    ref = ref.strip()
    m = re.match(r"^(.+?)[\s.]+(\d+)(?::(\d+)(?:[-–](\d+))?)?$", ref)
    if not m:
        return None
    b = resolve_book(m.group(1))
    if not b:
        return None
    ch = int(m.group(2))
    v1 = int(m.group(3)) if m.group(3) else None
    v2 = int(m.group(4)) if m.group(4) else v1
    return {"book": b, "chapter": ch, "verse": v1, "verse_end": v2}

def ref_label(book: str, chapter: int, verse: int | None = None) -> str:
    return f"{book} {chapter}" + (f":{verse}" if verse else "")

def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def strip_hebrew_points(s: str) -> str:
    return "".join(c for c in s if "\u05d0" <= c <= "\u05ea")

def strip_greek_accents(s: str) -> str:
    return strip_accents(s).lower()

# ── Curated book context channel ─────────────────────────────────────
# Kept deliberately compact. These are orientation notes, not doctrine.
_BOOK_CONTEXT_ROWS = {
"Genesis": ("traditionally Moses", "c. 1445–1405 BC (traditional); text likely shaped over time", "narrative / primeval history / patriarchal narrative", "Israel", "Origins: creation, rupture, covenant family, and the promise carried through failure", "liturgical + common", "The Bible's opening narrative: God creates, humanity fractures, and God binds himself to a family."),
"Exodus": ("traditionally Moses", "c. 1445 BC (traditional)", "narrative / law / covenant document", "Israel in the wilderness", "Deliverance from Egypt and constitution of Israel as a covenant people", "official + liturgical", "The paradigm rescue story: plague, sea, Sinai, law, tabernacle, and the golden calf."),
"Leviticus": ("traditionally Moses", "c. 1445 BC (traditional)", "law / ritual manual", "Israel / priests", "How a holy God may be approached and how a redeemed people must live", "official + liturgical", "Worship, sacrifice, purity, atonement, and holiness encoded as ritual."),
"Numbers": ("traditionally Moses", "c. 1445–1405 BC (traditional)", "narrative / law / travel itinerary", "wilderness generation", "The long journey from Sinai to Moab and the cost of unbelief", "official + common", "A generation dies in the wilderness; God's promise survives their failure."),
"Deuteronomy": ("traditionally Moses", "c. 1406 BC (traditional)", "covenant renewal / sermon / law", "Israel on the plains of Moab", "Renew covenant loyalty before entering the land", "official + liturgical", "Moses' farewell sermons: love YHWH, remember, obey, and choose life."),
"Joshua": ("anonymous; tradition associates Joshua", "c. 1400–1370 BC (traditional)", "narrative / conquest account", "Israel in Canaan", "God gives the land and calls Israel to covenant faithfulness", "official + common", "Entry into the land, Jericho, conquest, distribution, and covenant renewal."),
"Judges": ("anonymous", "c. 1200–1050 BC settings", "narrative / cyclical history", "Israel in the pre-monarchy period", "What happens when everyone does what is right in their own eyes", "common", "A spiral of apostasy, oppression, deliverance, and relapse under the judges."),
"Ruth": ("anonymous", "c. 1100 BC settings", "narrative / short story", "Israel / Bethlehem", "Loyal love and redemption across ethnic and social boundaries", "common + liturgical", "A Moabite widow becomes the great-grandmother of David through hesed."),
"1Samuel": ("anonymous; tradition associates Samuel", "c. 1100–1010 BC", "narrative", "Israel", "The birth of monarchy and the contrast between Saul and David", "official + common", "Samuel, Saul, and the rise of David: obedience versus self-rule."),
"2Samuel": ("anonymous", "c. 1010–970 BC", "narrative", "Israel", "David's reign, covenant, sin, and consequence", "official + common", "David's throne is established, then fractured by Bathsheba, Absalom, and the sword."),
"1Kings": ("anonymous", "c. 970–853 BC", "narrative / royal annals", "Israel and Judah", "Solomon's glory, the divided kingdom, and the Elijah contest", "official + common", "Temple, division, idolatry, and prophets confronting royal power."),
"2Kings": ("anonymous", "c. 853–560 BC", "narrative / royal annals", "Israel and Judah", "The collapse and exile of both kingdoms", "official + common", "Elisha, reforming kings, Assyria, Babylon, and the road to exile."),
"1Chronicles": ("traditionally Ezra", "c. 450–400 BC", "genealogy / narrative / temple history", "post-exilic Judah", "Reassure the restored community of Davidic and temple continuity", "official + liturgical", "A retelling of Israel's story centered on David, worship, and the temple."),
"2Chronicles": ("traditionally Ezra", "c. 450–400 BC", "narrative / temple history", "post-exilic Judah", "Temple faithfulness as the key to national well-being", "official + liturgical", "Solomon's temple through the fall of Jerusalem, ending with Cyrus' decree."),
"Ezra": ("Ezra (traditional)", "c. 458–430 BC", "narrative / official correspondence", "post-exilic Judah", "Rebuild the temple and reconstitute the covenant community", "official + liturgical", "Return from exile, temple reconstruction, and covenant reform; contains Aramaic official documents."),
"Nehemiah": ("Nehemiah", "c. 445–430 BC", "memoir / narrative", "post-exilic Judah", "Rebuild Jerusalem's walls and renew covenant life", "official + common", "A cupbearer's prayer, a ruined wall, and a rebuilt community."),
"Esther": ("anonymous", "c. 480–465 BC settings", "narrative / court tale", "Persian diaspora", "God's hidden providence preserves his people", "official + liturgical", "A queen risks her life to stop genocide; God is never named but everywhere implied."),
"Job": ("anonymous", "c. 1000–600 BC (debated)", "poetry / wisdom dialogue", "Israel / ancient Near East", "Wrestle honestly with innocent suffering and God's freedom", "common + liturgical", "A righteous man loses everything and demands an answer from God."),
"Psalms": ("David and others", "c. 1000–400 BC", "poetry / hymnbook / prayer", "Israel / temple", "Teach Israel to pray in every human condition", "liturgical", "150 prayers and songs: praise, lament, trust, penitence, and protest."),
"Proverbs": ("Solomon and others", "c. 950–400 BC", "wisdom / poetry / instruction", "Israel / youth", "Form character through the fear of YHWH and practical wisdom", "common + official", "Short sayings on speech, work, money, desire, friendship, and folly."),
"Ecclesiastes": ("the Preacher / Qoheleth", "c. 450–250 BC (debated)", "wisdom / philosophical reflection", "Israel / educated reader", "Face the limits of life and receive good as gift", "common + liturgical", "A relentless probe of hevel: vapor, brevity, death, and joy."),
"SongofSolomon": ("Solomon (traditional)", "c. 950 BC (traditional)", "poetry / love song", "Israel", "Celebrate covenant love and desire", "liturgical + common", "A lyric dialogue of longing, union, loss, and delight."),
"Isaiah": ("Isaiah", "c. 740–680 BC (chs. 1–39); later shaping (chs. 40–66)", "prophecy / poetry / vision", "Judah and Jerusalem", "Judgment and comfort: YHWH alone is holy, sovereign, and saving", "official + liturgical + common", "A prophet sees the Holy One, warns kings, and announces a servant who saves."),
"Jeremiah": ("Jeremiah", "c. 627–580 BC", "prophecy / poetry / prose sermons", "Judah", "Covenant indictment and the promise of a new covenant", "official + common", "A reluctant prophet lives through Jerusalem's fall and announces restoration."),
"Lamentations": ("anonymous (traditionally Jeremiah)", "c. 586 BC", "poetry / lament", "survivors of Jerusalem", "Give words to catastrophic grief while holding onto covenant mercy", "liturgical", "Five acrostic laments over the ruined city: 'great is your faithfulness.'"),
"Ezekiel": ("Ezekiel", "c. 593–571 BC", "prophecy / vision / symbolic action", "Judean exiles in Babylon", "God's glory departs, then returns; dry bones live", "official + liturgical", "A priest-prophet sees the throne, the ruined temple, and a rebuilt city."),
"Daniel": ("Daniel (traditional)", "c. 605–530 BC settings; final form later", "narrative / apocalyptic vision", "exiles / persecuted faithful", "God rules the kingdoms of men; remain faithful under empire", "official + liturgical", "Court stories and beasts: empire is temporary, the Ancient of Days is not. Contains long Aramaic sections."),
"Hosea": ("Hosea", "c. 750–715 BC", "prophecy / poetry", "northern Israel", "Unfaithful Israel is loved by a faithful God", "common + liturgical", "A prophet's painful marriage becomes a parable of covenant betrayal."),
"Joel": ("Joel", "c. 835–400 BC (debated)", "prophecy / poetry", "Judah", "Day of YHWH: judgment and the outpouring of the Spirit", "liturgical", "Locusts, repentance, and a promise that sons and daughters will prophesy."),
"Amos": ("Amos", "c. 760–750 BC", "prophecy / poetry", "northern Israel", "YHWH demands justice, not empty ritual", "common + official", "A shepherd from Tekoa indicts prosperity built on oppression."),
"Obadiah": ("Obadiah", "c. 586 BC or earlier", "prophecy", "Judah / Edom", "Pride and violence against God's people will be judged", "common", "The shortest OT book: Edom's gloating over Jerusalem's fall will not stand."),
"Jonah": ("anonymous / Jonah", "c. 780 BC settings", "narrative / prophetic satire", "Israel / Nineveh", "God's mercy reaches beyond Israel", "common + liturgical", "A reluctant prophet flees, is swallowed, preaches, and sulks when God relents."),
"Micah": ("Micah", "c. 735–700 BC", "prophecy / poetry", "Judah and Samaria", "Judge injustice and walk humbly with God", "common + liturgical", "Bethlehem's ruler, the mountain of YHWH, and 'do justly, love mercy.'"),
"Nahum": ("Nahum", "c. 663–612 BC", "prophecy / poetry", "Judah / Nineveh", "Nineveh's fall proves YHWH is a refuge and avenger", "common", "The other side of Jonah: empire's terror ends."),
"Habakkuk": ("Habakkuk", "c. 609–598 BC", "prophecy / dialogue / poetry", "Judah", "The righteous live by faith when God's justice seems delayed", "common + liturgical", "A prophet argues with God about violence and Babylon."),
"Zephaniah": ("Zephaniah", "c. 640–609 BC", "prophecy / poetry", "Judah", "The day of YHWH purges pride and leaves a humble remnant", "common + liturgical", "Cosmic judgment and a quiet promise: God sings over his people."),
"Haggai": ("Haggai", "c. 520 BC", "prophecy / short oracles", "post-exilic Judah", "Finish the temple; God's presence returns", "official + liturgical", "Four dated messages prod a stalled building project."),
"Zechariah": ("Zechariah", "c. 520–518 BC", "prophecy / visions / apocalyptic", "post-exilic Judah", "God restores temple, priesthood, and king", "official + liturgical", "Night visions, a crowned priest, and a pierced shepherd."),
"Malachi": ("Malachi", "c. 430 BC", "prophecy / disputation", "post-exilic Judah", "Covenant faithfulness, pure worship, and the coming messenger", "official + liturgical", "A closing courtroom scene: 'return to me and I will return to you.'"),
"Matthew": ("anonymous; tradition associates Matthew", "c. AD 50–70", "gospel / narrative / discourse", "Jewish-Christian readers", "Jesus is the Davidic Messiah, new Moses, and fulfillment of Scripture", "common + liturgical", "Genealogy, Sermon on the Mount, parables of the kingdom, passion, resurrection."),
"Mark": ("anonymous; tradition associates Mark", "c. AD 50–70", "gospel / narrative", "Roman / Gentile Christians", "Jesus is the suffering Son of God; discipleship is the cross", "common", "Fast-paced: baptism, exorcisms, misunderstandings, and the way of the cross."),
"Luke": ("Luke", "c. AD 60–80", "gospel / narrative / history", "Theophilus / Gentile readers", "Jesus is Savior for the outsider, the poor, and the nations", "common + liturgical", "A carefully ordered account from Bethlehem to Emmaus, with parables of mercy."),
"John": ("anonymous; tradition associates John", "c. AD 70–100", "gospel / narrative / discourse", "Christian communities / seekers", "Jesus is the incarnate Word; believe and have life", "common + liturgical", "Seven signs, long discourses, footwashing, and the hour of glory."),
"Acts": ("Luke", "c. AD 60–90", "narrative / history", "Theophilus / early church", "The Spirit sends the gospel from Jerusalem to Rome", "official + common", "Pentecost, prison, shipwreck, and an unstoppable mission."),
"Romans": ("Paul", "c. AD 56–58", "epistle / theological argument", "Christians in Rome", "The gospel is God's righteousness for Jew and Gentile by faith", "official + common", "Paul's most sustained argument: sin, justification, Israel, and the new life."),
"1Corinthians": ("Paul", "c. AD 53–54", "epistle / pastoral response", "church at Corinth", "The cross reshapes community, sexuality, worship, and resurrection hope", "common + official", "Answers to a divided, gifted, disordered church."),
"2Corinthians": ("Paul", "c. AD 55–56", "epistle / apostolic defense", "church at Corinth", "True apostleship is weakness and suffering for the gospel", "common + official", "Paul defends his ministry, boasts in weakness, and calls for reconciliation."),
"Galatians": ("Paul", "c. AD 48–55", "epistle / polemic", "churches in Galatia", "Justification by faith in Christ, not law-keeping", "common + official", "A fiery letter: one gospel, one family, freedom in the Spirit."),
"Ephesians": ("Paul", "c. AD 60–62", "epistle / theological meditation", "churches in Asia Minor", "God's cosmic plan unites Jew and Gentile in Christ", "official + liturgical", "Blessings, mystery, household code, and the armor of God."),
"Philippians": ("Paul", "c. AD 60–62", "epistle / friendship letter", "church at Philippi", "Joy and unity through the self-emptying mind of Christ", "common + liturgical", "A prison letter about rejoicing, humility, and knowing Christ."),
"Colossians": ("Paul", "c. AD 60–62", "epistle / doctrinal correction", "church at Colossae", "Christ is supreme over every power; live from that fullness", "official + liturgical", "A hymn of cosmic Christology against ascetic and angelic religion."),
"1Thessalonians": ("Paul", "c. AD 50–51", "epistle / pastoral encouragement", "church at Thessalonica", "Hope and holiness while waiting for the Lord's return", "common + official", "The earliest surviving Pauline letter: faith, love, and the day of the Lord."),
"2Thessalonians": ("Paul", "c. AD 51–52", "epistle / correction", "church at Thessalonica", "Clarify the return of Christ and steady the idle", "common + official", "Do not be shaken; the man of lawlessness must come first."),
"1Timothy": ("Paul", "c. AD 62–64", "epistle / pastoral manual", "Timothy / Ephesus", "Order the church around sound doctrine and godly leadership", "official + common", "Instructions on elders, widows, money, and false teaching."),
"2Timothy": ("Paul", "c. AD 64–67", "epistle / farewell", "Timothy", "Guard the deposit and endure suffering to the end", "official + common", "Paul's last letter: Scripture, succession, and the crown."),
"Titus": ("Paul", "c. AD 62–64", "epistle / pastoral manual", "Titus / Crete", "Grace produces good works and ordered churches", "official + common", "Appoint elders, silence false teachers, live soberly."),
"Philemon": ("Paul", "c. AD 60–62", "epistle / personal appeal", "Philemon", "Receive Onesimus as a brother, not a slave", "common", "A one-page masterpiece of persuasion and Christian social transformation."),
"Hebrews": ("anonymous", "c. AD 60–90", "sermon / epistle / homily", "Jewish-Christian readers", "Jesus is superior to angels, Moses, priesthood, and sacrifice", "official + liturgical", "A sustained argument for perseverance: fix your eyes on Jesus."),
"James": ("James (traditional)", "c. AD 45–60", "epistle / wisdom instruction", "scattered Jewish Christians", "Faith that does not act is dead", "common", "Proverbs-like teaching on trials, speech, favoritism, and prayer."),
"1Peter": ("Peter", "c. AD 60–65", "epistle / pastoral encouragement", "exiles in Asia Minor", "Hope and holiness under suffering", "common + liturgical", "A baptismal letter: living stones, holy exiles, and grace under pressure."),
"2Peter": ("Peter (traditional)", "c. AD 65–90", "epistle / testament", "church facing false teaching", "Grow in knowledge and wait for the day of the Lord", "official + common", "A farewell warning against scoffers and distortion."),
"1John": ("anonymous; tradition associates John", "c. AD 85–100", "epistle / homily", "churches facing division", "Assurance: God is light, love, and life; abide in Christ", "common + liturgical", "Tests of truth and love, and the confidence of children of God."),
"2John": ("the Elder (traditionally John)", "c. AD 85–100", "epistle / short letter", "elect lady and her children", "Hold truth and love together; reject deceivers", "common", "A postcard about walking in love and guarding the doctrine of Christ."),
"3John": ("the Elder (traditionally John)", "c. AD 85–100", "epistle / short letter", "Gaius", "Support faithful missionaries; resist ambition", "common", "A personal note praising hospitality and exposing Diotrephes."),
"Jude": ("Jude", "c. AD 65–90", "epistle / polemic", "beloved called ones", "Contend for the faith and keep yourselves in God's love", "common + liturgical", "A urgent warning against corruption, ending in doxology."),
"Revelation": ("John (traditional)", "c. AD 90–96", "apocalyptic prophecy / letters / visions", "seven churches in Asia Minor", "The Lamb reigns; hold on, witness, and worship", "liturgical + official", "Symbolic visions of empire, judgment, the throne, and the new creation."),
}

BOOK_CONTEXT = {
    full: dict(zip(("author", "date", "genre", "audience", "purpose", "register", "summary"), row))
    for full, row in _BOOK_CONTEXT_ROWS.items()
}

# ── Curated mixed-language events ────────────────────────────────────
# lang: arc = Aramaic, heb = Hebrew, grc = Greek, lat = Latin.
# scope: verse (whole verse) or words (subset); `words` is 1-based token range.
LANG_EVENTS = [
    ("Gen.31.47", "arc", "words", "29-30", "Aramaic place-name יְגַר שָׂהֲדוּתָא ('witness heap') inside a Hebrew narrative; the narrator immediately supplies the Hebrew equivalent גַּלְעֵד."),
    ("Jer.10.11", "arc", "verse", "", "The only fully Aramaic verse in Jeremiah: a polemical formula addressed to the nations about idols."),
    ("Dan.2.4", "arc", "words", "4-", "Daniel switches from Hebrew to Aramaic mid-verse at the Chaldeans' reply; Aramaic continues through 7:28."),
    ("Dan.7.28", "heb", "verse", "", "Aramaic section ends; Hebrew resumes at 8:1."),
    ("Ezra.4.8", "arc", "words", "1-", "Aramaic official correspondence begins; continues through 6:18."),
    ("Ezra.6.18", "heb", "verse", "", "Hebrew narrative resumes after the Aramaic documents."),
    ("Ezra.7.12", "arc", "verse", "", "Aramaic royal letter of Artaxerxes; continues through 7:26."),
    ("Matt.27.46", "arc", "words", "1-", "Jesus' cry ἠλὶ ἠλὶ λεμὰ σαβαχθάνι preserves Aramaic/Hebrew words inside Greek narrative (Ps 22:1)."),
    ("Mark.5.41", "arc", "words", "8-9", "ταλιθα κουμ ('Talitha koum') is Aramaic, translated by the narrator."),
    ("Mark.7.34", "arc", "words", "7-8", "εφφαθα ('Ephphatha') is Aramaic, translated by the narrator."),
    ("Mark.14.36", "arc", "words", "2-2", "αββα ('Abba') is Aramaic, retained in Greek prayer language."),
    ("Mark.15.34", "arc", "words", "4-", "ελοι ελοι λεμα σαβαχθανι preserves Semitic words inside Greek narrative."),
    ("John.1.42", "arc", "words", "40-42", "Κηφᾶς (Cephas) is an Aramaic name explained as Πέτρος."),
    ("John.5.2", "arc", "words", "1-6", "Βηθεσδά / Βηθζαθά place-name traditions preserve Semitic forms."),
    ("John.19.13", "arc", "words", "11-13", "Γαββαθα (Gabbatha) is a Semitic place-name explained in Greek."),
    ("John.19.17", "arc", "words", "4-6", "Γολγοθᾶ (Golgotha) is a Semitic place-name explained in Greek."),
    ("John.19.20", "lat", "verse", "", "The titulus is written in Hebrew, Latin, and Greek; the Gospel notes all three languages."),
    ("John.20.16", "arc", "words", "10-12", "Ραββουνι (Rabboni) is a Semitic title explained as 'Teacher'."),
    ("Acts.1.19", "arc", "words", "12-14", "Ἀκελδαμά (Aceldama) is a Semitic field-name explained in Greek."),
    ("Acts.9.36", "arc", "words", "1-2", "Ταβιθά (Tabitha) is a Semitic name translated as Δορκάς."),
    ("Acts.21.37", "heb", "words", "1-", "The tribune asks whether Paul knows Greek; Paul's Jerusalem speech (22:2) is heard in Hebrew/Aramaic."),
    ("Acts.22.2", "heb", "verse", "", "Paul addresses the Jerusalem crowd in Hebrew/Aramaic, which silences them."),
    ("Acts.26.14", "heb", "words", "9-", "The voice from heaven speaks to Saul in Hebrew/Aramaic."),
    ("1Cor.16.22", "arc", "words", "3-4", "μαράνα θά ('Maranatha') is an Aramaic liturgical formula."),
    ("Rom.8.15", "arc", "words", "9-10", "αββα ('Abba') retained as an Aramaic address to the Father."),
    ("Gal.4.6", "arc", "words", "10-11", "αββα ('Abba') retained as an Aramaic address to the Father."),
    ("Rev.9.11", "heb", "words", "7-9", "Ἀβαδδών (Abaddon) is a Hebrew name glossed by Greek Ἀπολλύων."),
    ("Rev.16.16", "heb", "words", "6-7", "Ἁρμαγεδών (Armageddon) is a Semitic place-name."),
    ("Luke.23.38", "lat", "verse", "", "The inscription above Jesus is written in Greek, Latin, and Hebrew."),
]

# ── Koine Greek → Galilean Aramaic bridge (reconstruction) ───────────
# This is a scholarly-proxy channel, not a manuscript. `confidence`:
# high = well-attested lexical equivalent; medium = likely; low = speculative.
ARAMAIC_BRIDGE = [
    # greek_strong, greek_lemma, aramaic, translit, gloss, confidence, note
    ("G3056", "λόγος", "מימרא", "memra", "word, utterance, self-expression", "high", "Targumic memra is the closest Semitic idiom for John's Logos; מלה (mela) is the everyday word."),
    ("G2316", "θεός", "אלהא", "alaha", "God", "high", "Standard Syriac/Jewish Aramaic term."),
    ("G2962", "κύριος", "מרא", "mara", "lord, master", "high", "Also יהוה in scripture quotations; mara is the common title."),
    ("G2424", "Ἰησοῦς", "ישוע", "Yeshua", "Jesus / Yehoshua", "high", "Galilean pronunciation likely Yeshu(a)."),
    ("G5547", "Χριστός", "משיחא", "meshiha", "anointed one, Messiah", "high", "Greek Christos translates Aramaic meshiha."),
    ("G4151", "πνεῦμα", "רוחא", "ruha", "spirit, wind, breath", "high", "Same semantic range as Hebrew ruach."),
    ("G5590", "ψυχή", "נפשא", "naphsha", "soul, self, life", "high", "Cognate of Hebrew nephesh."),
    ("G26", "ἀγάπη", "רחמא", "rahma", "love, compassion", "medium", "Aramaic prefers rahma/huba; agape's covenant nuance is carried by context."),
    ("G25", "ἀγαπάω", "רחם", "reham", "to love, show mercy", "medium", "Verb form of rahma."),
    ("G4102", "πίστις", "הימנותא", "haymanutha", "faithfulness, trust", "high", "Cognate of Hebrew emunah."),
    ("G5485", "χάρις", "טיבותא", "taybutha", "favor, goodness, grace", "high", "Common Syriac term for grace."),
    ("G1515", "εἰρήνη", "שלמא", "shlama", "peace, wholeness", "high", "Cognate of Hebrew shalom."),
    ("G932", "βασιλεία", "מלכותא", "malkutha", "kingdom, reign", "high", "Cognate of Hebrew malkuth."),
    ("G3962", "πατήρ", "אבא", "abba", "father", "high", "Retained untranslated in the NT (Mk 14:36; Rom 8:15; Gal 4:6)."),
    ("G5207", "υἱός", "ברא", "bera", "son", "high", "Cognate of Hebrew ben."),
    ("G935", "βασιλεύς", "מלכא", "malka", "king", "high", "Cognate of Hebrew melek."),
    ("G4521", "σάββατον", "שבתא", "shabta", "Sabbath", "high", "Cognate of Hebrew shabbat."),
    ("G1577", "ἐκκλησία", "כנישתא", "knishta", "assembly, synagogue, church", "high", "The same word covers synagogue and church."),
    ("G908", "βάπτισμα", "טבילותא", "tebhilutha", "immersion, baptism", "high", "From tebal, to immerse."),
    ("G3341", "μετάνοια", "תיובתא", "tiyuvta", "repentance, turning", "high", "From tuv, to return."),
    ("G266", "ἁμαρτία", "חטיתא", "hetitha", "sin, missing the mark", "high", "Cognate of Hebrew hata."),
    ("G1343", "δικαιοσύνη", "זדיקותא", "zaddiqutha", "righteousness, justice", "high", "Cognate of Hebrew tsedaqah."),
    ("G165", "αἰών", "עלמא", "alma", "age, world, eternity", "high", "Cognate of Hebrew olam."),
    ("G281", "ἀμήν", "אמין", "amin", "amen, surely", "high", "Liturgical affirmation retained in Greek."),
    ("G5", "ἀββά", "אבא", "abba", "father", "high", "Directly retained in the NT."),
    ("G4461", "ῥαββί", "רבי", "rabbi", "my master, teacher", "high", "Retained as a title in the Gospels."),
    ("G4462", "ῥαββουνί", "רבוני", "rabbuni", "my great master", "high", "Retained in Mk 10:51; Jn 20:16."),
    ("G3126", "μαμωνᾶς", "ממונא", "mamona", "wealth, money", "high", "Loanword retained in Greek."),
    ("G2878", "κορβᾶν", "קרבנא", "qorbana", "offering, dedicated gift", "high", "Retained in Mk 7:11."),
    ("G5028", "τάφος", "קברא", "qabra", "grave, tomb", "high", "Cognate of Hebrew qever."),
    ("G4074", "Πέτρος", "כאפא", "kepha", "rock, stone", "high", "The Greek name translates the Aramaic nickname."),
    ("G2786", "Κηφᾶς", "כאפא", "kepha", "rock, stone", "high", "Transliterated Aramaic nickname."),
    ("G907", "βαπτίζω", "טבל", "tebal", "to immerse", "high", "Cognate/loan relationship."),
    ("G2098", "εὐαγγέλιον", "בשורתא", "besartha", "good news, gospel", "high", "From basar, to announce good news."),
    ("G652", "ἀπόστολος", "שליחא", "shliha", "sent one, apostle", "high", "From shelah, to send."),
    ("G3107", "μακάριος", "טובי", "tuvei", "blessed, happy", "high", "The Aramaic beatitude opening (tuvei)."),
    ("G2288", "θάνατος", "מותא", "mawtha", "death", "high", "Cognate of Hebrew mavet."),
    ("G2222", "ζωή", "חיא", "hayya", "life", "high", "Cognate of Hebrew hayyim."),
    ("G5457", "φῶς", "נוהרא", "nuhra", "light", "high", "Cognate of Hebrew or."),
    ("G4655", "σκότος", "חושכא", "hushka", "darkness", "high", "Cognate of Hebrew hoshekh."),
    ("G1093", "γῆ", "ארעא", "ara", "earth, land", "high", "Cognate of Hebrew erets."),
    ("G3772", "οὐρανός", "שמיא", "shmaya", "heaven(s)", "high", "Cognate of Hebrew shamayim."),
    ("G5204", "ὕδωρ", "מיא", "maya", "water", "high", "Cognate of Hebrew mayim."),
    ("G740", "ἄρτος", "לחמא", "lahma", "bread", "high", "Cognate of Hebrew lechem."),
    ("G3631", "οἶνος", "חמרא", "hamra", "wine", "high", "Cognate of Hebrew yayin."),
    ("G4864", "συναγωγή", "כנישתא", "knishta", "synagogue, assembly", "high", "Same word as ekklesia in Aramaic."),
    ("G40", "ἅγιος", "קדישא", "qaddisha", "holy, set apart", "high", "Cognate of Hebrew qadosh."),
    ("G4991", "σωτηρία", "פורקנא", "purqana", "salvation, rescue", "high", "From peraq, to redeem."),
    ("G3084", "λυτρόω", "פרוק", "peroq", "to redeem, ransom", "high", "Cognate of Hebrew padah/paraq."),
    ("G5479", "χαρά", "חדותא", "hadutha", "joy", "high", "Cognate of Hebrew simchah/hadut."),
    ("G5218", "ὑπακοή", "משמעתא", "mashmatta", "obedience, hearing", "high", "From shema, to hear/obey."),
    ("G3142", "μαρτύριον", "סהדותא", "sahdutha", "testimony, witness", "high", "Cognate of Hebrew edut."),
    ("G3498", "νεκρός", "מיתא", "mitha", "dead", "high", "Cognate of Hebrew met."),
    ("G450", "ἀνίστημι", "קום", "qum", "to rise, stand up", "high", "Cognate of Hebrew qum."),
    ("G191", "ἀκούω", "שמע", "shema", "to hear, obey", "high", "Cognate of Hebrew shama."),
    ("G2983", "λαμβάνω", "קבל", "qabel", "to receive, take", "high", "Common Aramaic verb."),
    ("G1437", "ἐάν", "אן", "in", "if", "medium", "Conditional particle; syntax differs."),
    # Directly retained Aramaic words in the Greek NT (not reconstructions).
    ("G5008", "ταλιθα", "טליתא", "talitha", "little girl", "high", "Mark 5:41, retained and translated by Mark."),
    ("G2891", "κουμ", "קום", "qum", "arise, stand up", "high", "Mark 5:41, retained Aramaic imperative."),
    ("G2188", "εφφαθα", "אתפתח", "etpethach", "be opened", "high", "Mark 7:34, retained Aramaic passive imperative."),
    ("G1682", "ελωι", "אלהי", "elahi", "my God", "high", "Mark 15:34, Aramaic form of the cry."),
    ("G2982", "λεμα", "למא", "lema", "why", "high", "Mark 15:34, retained Aramaic."),
    ("G4518", "σαβαχθανι", "שבקתני", "shebaqtani", "you have forsaken me", "high", "Mark 15:34 / Matt 27:46, retained Aramaic."),
    ("G1115", "γολγοθα", "גלגלתא", "gulgalta", "skull, place of the skull", "high", "Retained Aramaic place name."),
    ("G1042", "γαββαθα", "גבתא", "gabbeta", "raised place, platform", "medium", "John 19:13, retained Semitic place name."),
]

# ── Source registry ──────────────────────────────────────────────────
SOURCES = {
    "kjv": {"name": "King James Version (1769)", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/KJV.db"},
    "asv": {"name": "American Standard Version (1901)", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/ASV.db"},
    "nheb": {"name": "New Heart English Bible", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/NHEB.db"},
    "ylt": {"name": "Young's Literal Translation", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/YLT.db"},
    "darby": {"name": "Darby Translation", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/Darby.db"},
    "bbe": {"name": "Bible in Basic English", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/BBE.db"},
    "webster": {"name": "Webster Bible", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/Webster.db"},
    "geneva": {"name": "Geneva Bible (1599)", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/Geneva1599.db"},
    "vulgate": {"name": "Latin Vulgate", "kind": "translation", "license": "Public domain", "path": "src/scrollmapper/Vulgate.db"},
    "stepbible": {"name": "STEPBible TAHOT/TAGNT + lexicons", "kind": "original_language", "license": "CC BY 4.0", "path": "src/stepbible"},
    "lxx": {"name": "Septuagint (Rahlfs 1935)", "kind": "ancient_version", "license": "CC BY-NC-SA 4.0", "path": "src/lxx/LXX1.SQLite3"},
    "openbible_xref": {"name": "OpenBible cross references", "kind": "cross_reference", "license": "CC BY", "path": "src/xrefs/cross_references.txt"},
    "nave": {"name": "Nave's Topical Bible", "kind": "topical", "license": "Public domain", "path": "src/commentary/nave-entries.jsonl"},
    "torrey": {"name": "Torrey's Topical Textbook", "kind": "topical", "license": "Public domain", "path": "src/commentary/torrey-entries.jsonl"},
    "calvin": {"name": "John Calvin Commentaries", "kind": "commentary", "license": "Public domain", "path": "src/commentary/pillar/c/calvin"},
    "fbmeyer": {"name": "F. B. Meyer, Through the Bible Day by Day", "kind": "commentary", "license": "Public domain", "path": "src/commentary/pillar/c/fbmeyer"},
    "sefaria": {"name": "Sefaria (Targum, Rashi, Ibn Ezra, Ramban)", "kind": "commentary", "license": "CC BY / public domain", "path": "online"},
    "openscriptures_strongs": {"name": "Open Scriptures Strong's", "kind": "lexicon", "license": "Public domain", "path": "strongs"},
    "sdbh": {"name": "UBS Dictionary of Biblical Hebrew/Greek", "kind": "lexicon", "license": "CC BY-SA 4.0", "path": "sdbh"},
    "sahd": {"name": "Semantics of Ancient Hebrew Database", "kind": "cultural", "license": "CC BY 4.0", "path": "sahd"},
    "aramaic_root_atlas": {"name": "Aramaic Root Atlas — Peshitta & Targums", "kind": "ancient_version", "license": "Apache 2.0", "path": "src/aramaic"},
}
