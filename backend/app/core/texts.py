"""Fixed Indonesian texts used by the backend (fallbacks) and the mock AI."""

GREETING = "Halo! Selamat datang di Mitsubishi DIPO."

QUESTIONS = {
    "name": "Boleh tahu dengan Bapak/Ibu siapa?",
    "domicile": "Saat ini berdomisili di kota/kabupaten mana?",
    "vehicle": "Unit Mitsubishi apa yang sedang diminati?",
}

# Used when the customer's previous answer could not be accepted.
REASK = {
    "name": "Mohon maaf, boleh disebutkan nama Bapak/Ibu?",
    "domicile": "Mohon maaf, boleh disebutkan kota/kabupaten domisili Bapak/Ibu?",
    "vehicle": (
        "Mohon maaf, boleh disebutkan unit Mitsubishi yang diminati? Contohnya: {examples}."
    ),
}

NO_INFO = (
    "Mohon maaf, untuk {topic} saat ini belum ada informasi yang bisa saya sampaikan. "
    "Nanti tim sales kami yang akan menjelaskan detailnya."
)

TOPIC_LABELS = {
    "promo": "promo",
    "price": "harga",
    "dp": "DP (uang muka)",
    "installment": "angsuran/kredit",
    "dealer": "informasi dealer",
    "spec": "spesifikasi",
    "faq": "pertanyaan tersebut",
}

THANKS = "Terima kasih atas informasinya."


def with_name(name: str | None) -> str:
    return f"Baik, Bapak/Ibu {name}." if name else "Baik."
