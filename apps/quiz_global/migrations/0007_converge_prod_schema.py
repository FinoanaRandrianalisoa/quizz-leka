# Convergence du schéma de production (SQL idempotent).
#
# Les migrations 0004/0005/0006 sont enregistrées comme appliquées sur la base
# de production (Alwaysdata) mais leur DDL n'y a jamais réellement été exécutée :
# des colonnes (expired_at, abandoned_at) et des tables
# (QuizGlobalActivePlayer, QuizGlobalInvitation) peuvent manquer.
# Cette migration re-joue toutes les créations avec IF NOT EXISTS : elle est
# sans danger quel que soit l'état réel de la base.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quiz_global", "0006_fix_missing_columns_and_tables"),
    ]

    operations = [
        # ── Colonnes manquantes de quiz_global_quizglobalgame ──
        migrations.RunSQL(
            sql="""
                ALTER TABLE quiz_global_quizglobalgame
                ADD COLUMN IF NOT EXISTS expired_at TIMESTAMP WITH TIME ZONE;
                ALTER TABLE quiz_global_quizglobalgame
                ADD COLUMN IF NOT EXISTS abandoned_at TIMESTAMP WITH TIME ZONE;
                ALTER TABLE quiz_global_quizglobalgame
                ADD COLUMN IF NOT EXISTS mise NUMERIC(18, 2) NOT NULL DEFAULT 0;
                ALTER TABLE quiz_global_quizglobalgame
                ADD COLUMN IF NOT EXISTS mise_proposee_invite NUMERIC(18, 2);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # ── Table QuizGlobalActivePlayer ──
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS quiz_global_quizglobalactiveplayer (
                    player_id INTEGER NOT NULL PRIMARY KEY REFERENCES users_utilisateur(id) ON DELETE CASCADE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    game_id INTEGER NOT NULL REFERENCES quiz_global_quizglobalgame(id) ON DELETE CASCADE
                );
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # ── Table QuizGlobalInvitation (colonne + contrainte + index) ──
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS quiz_global_quizglobalinvitation (
                    id SERIAL NOT NULL PRIMARY KEY,
                    status VARCHAR(12) NOT NULL DEFAULT 'PENDING',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    responded_at TIMESTAMP WITH TIME ZONE,
                    game_id INTEGER NOT NULL REFERENCES quiz_global_quizglobalgame(id) ON DELETE CASCADE,
                    receiver_id INTEGER NOT NULL REFERENCES users_utilisateur(id) ON DELETE CASCADE,
                    sender_id INTEGER NOT NULL REFERENCES users_utilisateur(id) ON DELETE CASCADE,
                    CONSTRAINT quiz_global_unique_invitee UNIQUE (game_id, receiver_id)
                );
                CREATE INDEX IF NOT EXISTS quiz_global_receive_72b972_idx
                    ON quiz_global_quizglobalinvitation (receiver_id, status);
                CREATE INDEX IF NOT EXISTS quiz_global_game_id_a562c8_idx
                    ON quiz_global_quizglobalinvitation (game_id, status);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # ── Rattrapage si la table existait déjà sans contrainte/index ──
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'quiz_global_unique_invitee'
                    ) THEN
                        ALTER TABLE quiz_global_quizglobalinvitation
                        ADD CONSTRAINT quiz_global_unique_invitee UNIQUE (game_id, receiver_id);
                    END IF;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]