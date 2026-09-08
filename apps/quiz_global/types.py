import strawberry

from apps.quiz_global.services import serialize_game


@strawberry.type
class QuizGlobalThemeAvailability:
    id: int
    nom: str
    icone: str
    remaining: int
    selectable: bool


@strawberry.type
class QuizGlobalPlayerView:
    id: str
    pseudo: str
    seat: str
    score: int


@strawberry.type
class QuizGlobalOptions:
    A: str
    B: str
    C: str
    D: str


@strawberry.type
class QuizGlobalQuestionView:
    id: int
    turn_number: int
    theme: str
    question: str
    is_tie_break: bool
    options: QuizGlobalOptions | None
    correct_option: str | None
    correct_text: str | None


@strawberry.type
class QuizGlobalMyAnswer:
    selected_option: str
    status: str
    points_awarded: int | None


@strawberry.type
class QuizGlobalResultLine:
    seat: str
    pseudo: str
    selected_option: str | None
    is_correct: bool
    points_awarded: int


@strawberry.type
class QuizGlobalState:
    game_id: int
    status: str
    target_questions: int
    current_turn: int
    active_seat: str
    is_tie_break: bool
    mise: str
    mise_effective: str
    phase_started_at: str | None
    phase_deadline: str | None
    server_time: str
    themes: list[QuizGlobalThemeAvailability]
    player_a: QuizGlobalPlayerView | None
    player_b: QuizGlobalPlayerView | None
    invited_player: QuizGlobalPlayerView | None
    winner_id: str | None
    question: QuizGlobalQuestionView | None
    my_answer: QuizGlobalMyAnswer | None
    my_seat: str | None
    results: list[QuizGlobalResultLine] | None = None


def state_from_payload(payload: dict) -> QuizGlobalState:
    question = None
    if payload.get("question"):
        q = payload["question"]
        opts = q.get("options")
        question = QuizGlobalQuestionView(
            id=q["id"],
            turn_number=q["turnNumber"],
            theme=q["theme"],
            question=q["question"],
            is_tie_break=q["isTieBreak"],
            options=QuizGlobalOptions(**opts) if opts else None,
            correct_option=q.get("correctOption"),
            correct_text=q.get("correctText"),
        )
    my_answer = None
    if payload.get("myAnswer"):
        a = payload["myAnswer"]
        my_answer = QuizGlobalMyAnswer(
            selected_option=a["selectedOption"],
            status=a["status"],
            points_awarded=a.get("pointsAwarded"),
        )
    results = None
    if payload.get("results"):
        results = [
            QuizGlobalResultLine(
                seat=r["seat"],
                pseudo=r["pseudo"],
                selected_option=r.get("selectedOption"),
                is_correct=r["isCorrect"],
                points_awarded=r["pointsAwarded"],
            )
            for r in payload["results"]
        ]
    pa = payload.get("playerA")
    pb = payload.get("playerB")
    inv = payload.get("invitedPlayer")
    return QuizGlobalState(
        game_id=payload["gameId"],
        status=payload["status"],
        target_questions=payload["targetQuestions"],
        current_turn=payload["currentTurn"],
        active_seat=payload["activeSeat"],
        is_tie_break=payload["isTieBreak"],
        mise=payload.get("mise", "0.00"),
        mise_effective=payload.get("miseEffective", "0.00"),
        phase_started_at=payload.get("phaseStartedAt"),
        phase_deadline=payload.get("phaseDeadline"),
        server_time=payload["serverTime"],
        themes=[QuizGlobalThemeAvailability(**t) for t in payload.get("themes") or []],
        player_a=QuizGlobalPlayerView(**pa) if pa else None,
        player_b=QuizGlobalPlayerView(**pb) if pb else None,
        invited_player=QuizGlobalPlayerView(**inv) if inv else None,
        winner_id=payload.get("winnerId"),
        question=question,
        my_answer=my_answer,
        my_seat=payload.get("mySeat"),
        results=results,
    )


def to_state(game, viewer) -> QuizGlobalState:
    return state_from_payload(serialize_game(game, viewer))
