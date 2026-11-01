"""Results (SAD 3.1): business operations on published results. The visibility rule is attempts.services.result_visible."""
from decimal import Decimal


def scorecard(attempt):
    """FR-027: everything the Student's scorecard shows, read from the stored evaluation -- nothing is re-scored.

    Returns {"score", "total_marks", "percentage", "passed", "rows"} where rows is one dict per question
    in paper order: {"n", "stem", "chosen" (option text or None), "marks" (Decimal, 0 when unanswered)}.
    Every question on the paper gets a row, answered or not (UT_062: all 25 lines).
    """
    answers = {a.question_id: a for a in attempt.answers.select_related("option")}
    rows = []
    for n, question in enumerate(attempt.exam.questions.order_by("examquestion__order"), start=1):
        answer = answers.get(question.id)
        if answer is not None and answer.option is not None:
            chosen = answer.option.text
            marks = answer.marks if answer.marks is not None else Decimal("0")
        else:
            chosen = None
            marks = Decimal("0")
        rows.append({
            "n": n,
            "stem": question.stem,
            "chosen": chosen,
            "marks": marks,
        })
    return {
        "score": attempt.score,
        "total_marks": attempt.exam.total_marks,
        "percentage": attempt.percentage,
        "passed": attempt.passed,
        "rows": rows,
    }
