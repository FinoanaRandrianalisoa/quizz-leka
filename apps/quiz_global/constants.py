"""Statuts des parties Quizz Global — source de vérité unique.

Un joueur ne peut participer qu'à UNE partie réellement active à la fois.
Toutes les parties terminées, annulées, expirées ou abandonnées sont
considérées comme inactives et ne doivent jamais bloquer le joueur.
"""

ACTIVE_STATUSES = frozenset(
    {
        "WAITING",
        "THEME_SELECTION",
        "QUESTION_READING",
        "ANSWERING",
        "QUESTION_FINISHED",
        "TIE_BREAK_THEME",
    }
)

INACTIVE_STATUSES = frozenset(
    {
        "FINISHED",
        "CANCELLED",
        "EXPIRED",
        "ABANDONED",
    }
)

ALL_STATUSES = ACTIVE_STATUSES | INACTIVE_STATUSES