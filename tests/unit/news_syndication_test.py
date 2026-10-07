"""Copy grouping does not conflate brief headlines or numerical corrections."""

from src.news.syndication import fingerprint, group_evidence

BODY = (
    "The synthetic central bank published its reviewed statement today and reported "
    "that inflation reached 2 percent during the previous reporting period."
)


def test_syndicated_body_groups_across_titles_but_preserves_every_source():
    articles = [
        dict(title="First headline", content=BODY, source="Primary", url="https://one.invalid/news"),
        dict(title="Different headline", content=BODY.replace(" ", "\n  "),
             source="Syndicator", url="https://two.invalid/news"),
    ]
    original = [dict(item) for item in articles]
    result = group_evidence(articles)
    assert len(result) == 1
    assert articles == original
    assert result[0]["title"] == "First headline"
    group = result[0]["syndication"]
    assert {copy["source"] for copy in group["copies"]} == {"Primary", "Syndicator"}
    assert group["independent_corroboration"] == "unverified"
    assert group["scope"] == "authorized_retrieved_batch_only"


def test_corrections_and_distinct_full_bodies_do_not_merge():
    assert fingerprint(dict(content=BODY)) != fingerprint(dict(content=BODY.replace("2 percent", "3 percent")))
    articles = [
        dict(url="https://one.invalid", summary=BODY, content=BODY),
        dict(url="https://two.invalid", summary=BODY, content=BODY + " Correction appended."),
    ]
    assert len(group_evidence(articles)) == 2


def test_short_headlines_and_unknown_text_are_not_corroboration_or_copy_proof():
    rows = [dict(title="Markets rise", summary="Markets rise", url=f"https://{host}.invalid")
            for host in ("one", "two")]
    result = group_evidence(rows)
    assert len(result) == 2
    assert all(row["syndication"]["method"] == "attributed_record_v1" for row in result)
    assert all(row["syndication"]["independent_corroboration"] == "unverified" for row in result)


def test_ephemeral_news_does_not_count_copies_as_sentiment_votes(monkeypatch):
    from src.tools import news

    rows = [dict(title="Inflation", summary=BODY, source=f"Copy {i}", url=f"https://copy{i}.invalid",
                 sentiment={"label": "bullish", "score": 1.0}) for i in range(3)]
    rows.append(dict(title="Other", summary=BODY.replace("2 percent", "3 percent"),
                     source="Other", url="https://other.invalid", sentiment={"label": "bearish", "score": -1.0}))
    monkeypatch.setattr(news, "_fetch_newsapi", lambda *args: rows)
    result = news.search_market_news("inflation")
    assert result["articles_found"] == 2
    assert result["avg_sentiment_score"] == 0
    assert len(result["articles"][0]["syndication"]["copies"]) == 3
    assert "not a trading signal" in result["evidence_note"]
