"""Каркас конектора Instagram — потребує офіційного Meta Graph API доступу.

Instagram належить Meta і використовує той самий Graph API, що й Facebook
(див. facebook.py). Прямого пошуку чужих постів/Direct-повідомлень за
ключовими словами API не надає. Доступний і дозволений сценарій:

- Instagram Graph API (для Business/Creator-акаунтів, якими ви керуєте):
  коментарі та згадки (@mentions) під ВАШИМИ власними публікаціями.
- Hashtag Search API: обмежений пошук публічних постів за конкретним
  хештегом (не довільним ключовим словом), з жорсткими лімітами запитів,
  і теж вимагає App Review.

Публічний контент чужих акаунтів поза цими двома механізмами Meta свідомо
не віддає стороннім застосункам — будь-який обхід цього через неофіційний
скрейпінг порушує умови використання Instagram.

Коли доступ буде отримано, реалізуйте fetch_matches() нижче через Instagram
Graph API (`GET /{ig-hashtag-id}/recent_media` тощо).
"""


async def fetch_matches(keywords: list[str]) -> list[dict]:
    """Повертає список знайдених збігів. Наразі не реалізовано — немає доступу до API."""
    raise NotImplementedError(
        "Instagram-конектор вимагає Meta Graph API доступу (App Review, "
        "Hashtag Search API). Див. докстрінг модуля та README.md."
    )
