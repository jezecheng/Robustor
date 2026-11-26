"""LLM 打标：只挂 approved 知识点、提升置信度、不收录模型编造的新词。"""

from __future__ import annotations


class _FakeChat:
    def complete_json(self, system: str, user: str) -> dict:
        assert "candidates" in user
        return {
            "items": [
                {
                    "id": 0,
                    "knowledge": [
                        {"name": "一元二次方程", "confidence": 0.92},
                        {"name": "模型编造的方法论", "confidence": 0.99},
                    ],
                }
            ]
        }


def test_tag_stage_llm_knowledge(client):
    from app.db import SessionLocal
    from app.models import Document, Problem, ProblemTag, Tag
    from app.pipeline.base import StageContext
    from app.pipeline.s6_tag import TagStage

    with SessionLocal() as session:
        document = Document(subject="math", source_name="llm-tag-test", page_count=1)
        session.add(document)
        session.flush()
        problem = Problem(
            document_id=document.id,
            subject="math",
            stem_latex="一元二次方程的解法",
            stem_text="一元二次方程的解法",
            status="draft",
        )
        session.add(problem)
        session.commit()

        try:
            ctx = StageContext(
                document_id=document.id, page_id=None, session=session, storage=None, config={}
            )
            result = TagStage(chat=_FakeChat()).run(ctx)

            links = session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).all()
            names = {
                tag.name: link.weight
                for link, tag in (
                    (link, session.get(Tag, link.tag_id)) for link in links
                )
            }
            assert names.get("一元二次方程") == 0.92
            assert result.stats["llm_tags"] >= 1
            assert result.stats["llm_unresolved"] >= 1
            assert session.query(Tag).filter(Tag.name == "模型编造的方法论").count() == 0
        finally:
            session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete()
            session.query(Problem).filter(Problem.id == problem.id).delete()
            session.query(Document).filter(Document.id == document.id).delete()
            session.commit()


def test_tag_stage_fallback_without_chat(client, monkeypatch):
    """没有可用模型时不报错，仍走本地词表。"""
    import app.pipeline.s6_tag as s6
    from app.db import SessionLocal
    from app.models import Document, Problem, Tag
    from app.pipeline.base import StageContext

    monkeypatch.setattr(s6, "get_chat_provider", lambda session=None: None)

    with SessionLocal() as session:
        document = Document(subject="math", source_name="local-tag-test", page_count=1)
        session.add(document)
        session.flush()
        problem = Problem(
            document_id=document.id,
            subject="math",
            stem_latex="一元二次方程",
            stem_text="一元二次方程",
            status="draft",
        )
        session.add(problem)
        session.commit()

        try:
            ctx = StageContext(
                document_id=document.id, page_id=None, session=session, storage=None, config={}
            )
            result = s6.TagStage(chat=None).run(ctx)
            assert result.ok is True
            assert result.stats["tags"] >= 1
            assert session.query(Tag).filter(Tag.name == "一元二次方程").count() >= 1
        finally:
            from app.models import ProblemTag

            session.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete()
            session.query(Problem).filter(Problem.id == problem.id).delete()
            session.query(Document).filter(Document.id == document.id).delete()
            session.commit()
