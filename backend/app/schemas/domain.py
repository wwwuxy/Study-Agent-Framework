from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class KnowledgeConcept(StrictModel):
    key: str = Field(min_length=1, max_length=80, pattern=r"^[\w-]+$")
    name: str = Field(min_length=1, max_length=160)
    module: str = Field(min_length=1, max_length=160)
    objectives: list[str] = Field(min_length=1, max_length=10)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    importance: int = Field(default=1, ge=1, le=5)
    minutes: int = Field(default=15, ge=5, le=120)
    source_status: Literal["model_generated_unverified"] = "model_generated_unverified"


class Curriculum(StrictModel):
    concepts: list[KnowledgeConcept] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def graph_is_valid(self):
        from app.knowledge.concept_graph import validate_graph

        validate_graph([c.model_dump() for c in self.concepts])
        return self


class Question(StrictModel):
    prompt: str = Field(min_length=1, max_length=5000)
    concept_keys: list[str] = Field(min_length=1, max_length=5)
    kind: Literal["choice", "short_answer"] = "choice"
    options: dict[str, str] = Field(default_factory=dict, max_length=6)
    answer: str = Field(min_length=1, max_length=5000)
    rubric: str = Field(min_length=1, max_length=5000)
    difficulty: int = Field(default=2, ge=1, le=5)

    @model_validator(mode="after")
    def answer_in_options(self):
        if self.kind == "choice" and (len(self.options) < 2 or self.answer not in self.options):
            raise ValueError("选择题需要至少两个选项，答案必须属于选项")
        if len(set(self.concept_keys)) != len(self.concept_keys):
            raise ValueError("题目知识点不能重复")
        return self


class QuestionBatch(StrictModel):
    items: list[Question] = Field(min_length=1, max_length=10)


class LessonContent(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=15000)
    example: str = Field(min_length=1, max_length=8000)
    exercises: list[Question] = Field(min_length=1, max_length=3)


class Grade(StrictModel):
    is_correct: bool | None
    confidence: Literal["high", "medium", "low"]
    feedback: str = Field(min_length=1, max_length=4000)
    misconceptions: list[str] = Field(default_factory=list, max_length=10)


class Hint(StrictModel):
    hint: str = Field(min_length=1, max_length=2000)
