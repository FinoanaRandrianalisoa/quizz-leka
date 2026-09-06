from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("themes", "0002_add_category"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="QuizGlobalGame",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("WAITING", "Waiting"),
                            ("STARTING", "Starting"),
                            ("THEME_SELECTION", "Theme Selection"),
                            ("QUESTION_READING", "Question Reading"),
                            ("ANSWERING", "Answering"),
                            ("QUESTION_FINISHED", "Question Finished"),
                            ("TIE_BREAK", "Tie Break"),
                            ("FINISHED", "Finished"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="WAITING",
                        max_length=40,
                    ),
                ),
                ("target_questions", models.PositiveSmallIntegerField()),
                ("current_turn", models.PositiveIntegerField(default=0)),
                ("active_seat", models.CharField(default="A", max_length=1)),
                ("phase_started_at", models.DateTimeField(blank=True, null=True)),
                ("phase_deadline", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "invited_player",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="users.utilisateur",
                    ),
                ),
                (
                    "winner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="quiz_global_wins",
                        to="users.utilisateur",
                    ),
                ),
            ],
            options={"ordering": ["-cree_le"]},
        ),
        migrations.CreateModel(
            name="QuizGlobalPlayer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("seat", models.CharField(choices=[("A", "Player A"), ("B", "Player B")], max_length=1)),
                ("score", models.PositiveIntegerField(default=0)),
                ("is_connected", models.BooleanField(default=False)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "game",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="players", to="quiz_global.quizglobalgame"),
                ),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="quiz_global_players",
                        to="users.utilisateur",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="QuizGlobalGameQuestion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("turn_number", models.PositiveIntegerField()),
                ("correct_option", models.CharField(max_length=1)),
                ("is_tie_break", models.BooleanField(default=False)),
                ("reading_started_at", models.DateTimeField(blank=True, null=True)),
                ("answering_started_at", models.DateTimeField(blank=True, null=True)),
                ("answer_deadline", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "game",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="game_questions", to="quiz_global.quizglobalgame"),
                ),
                (
                    "question",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="themes.question"),
                ),
                (
                    "theme",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="themes.theme"),
                ),
                (
                    "option_a",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="themes.reponse"),
                ),
                (
                    "option_b",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="themes.reponse"),
                ),
                (
                    "option_c",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="themes.reponse"),
                ),
                (
                    "option_d",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="themes.reponse"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="QuizGlobalPlayerAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("selected_option", models.CharField(max_length=1)),
                ("is_correct", models.BooleanField(null=True)),
                ("points_awarded", models.PositiveSmallIntegerField(default=0)),
                ("answered_at", models.DateTimeField()),
                (
                    "game_question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="player_answers",
                        to="quiz_global.quizglobalgamequestion",
                    ),
                ),
                (
                    "player",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="users.utilisateur"),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="quizglobalplayer",
            constraint=models.UniqueConstraint(fields=("game", "player"), name="quiz_global_unique_player"),
        ),
        migrations.AddConstraint(
            model_name="quizglobalplayer",
            constraint=models.UniqueConstraint(fields=("game", "seat"), name="quiz_global_unique_seat"),
        ),
        migrations.AddConstraint(
            model_name="quizglobalgamequestion",
            constraint=models.UniqueConstraint(fields=("game", "turn_number"), name="quiz_global_unique_turn"),
        ),
        migrations.AddConstraint(
            model_name="quizglobalgamequestion",
            constraint=models.UniqueConstraint(fields=("game", "question"), name="quiz_global_unique_question"),
        ),
        migrations.AddIndex(
            model_name="quizglobalgamequestion",
            index=models.Index(fields=["game", "turn_number"], name="quiz_global_game_id_turn_idx"),
        ),
        migrations.AddIndex(
            model_name="quizglobalgamequestion",
            index=models.Index(fields=["game", "question"], name="quiz_global_game_id_q_idx"),
        ),
        migrations.AddIndex(
            model_name="quizglobalgamequestion",
            index=models.Index(fields=["game", "theme"], name="quiz_global_game_id_th_idx"),
        ),
        migrations.AddConstraint(
            model_name="quizglobalplayeranswer",
            constraint=models.UniqueConstraint(fields=("game_question", "player"), name="quiz_global_one_answer_per_player_per_question"),
        ),
        migrations.AddIndex(
            model_name="quizglobalplayeranswer",
            index=models.Index(fields=["game_question", "player"], name="quiz_global_gq_player_idx"),
        ),
    ]
