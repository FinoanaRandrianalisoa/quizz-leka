# Generated manually to fix missing tables and columns on Railway using direct SQL

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quiz_global', '0005_add_missing_tables_and_fields'),
    ]

    operations = [
        # Add expired_at column if it doesn't exist
        migrations.RunSQL(
            sql="""
                ALTER TABLE quiz_global_quizglobalgame
                ADD COLUMN IF NOT EXISTS expired_at TIMESTAMP WITH TIME ZONE;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Add abandoned_at column if it doesn't exist
        migrations.RunSQL(
            sql="""
                ALTER TABLE quiz_global_quizglobalgame
                ADD COLUMN IF NOT EXISTS abandoned_at TIMESTAMP WITH TIME ZONE;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Create QuizGlobalActivePlayer table if it doesn't exist
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
        # Create QuizGlobalInvitation table if it doesn't exist
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
                CREATE INDEX IF NOT EXISTS quiz_global_receive_72b972_idx ON quiz_global_quizglobalinvitation (receiver_id, status);
                CREATE INDEX IF NOT EXISTS quiz_global_game_id_a562c8_idx ON quiz_global_quizglobalinvitation (game_id, status);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
