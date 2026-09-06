import secrets
import string

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


def generer_code_parrain() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


class UtilisateurManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email=None, password=None, **extra_fields):
        email = (email or "").strip() or None
        if email:
            email = self.normalize_email(email)
        if not email and not extra_fields.get("telephone") and not extra_fields.get("pseudo"):
            raise ValueError("Un email, un numéro de téléphone ou un pseudo est obligatoire.")
        fallback = extra_fields.get("pseudo") or (email or "").split("@")[0] or extra_fields.get("telephone") or ""
        extra_fields.setdefault("username", fallback)
        if not extra_fields.get("pseudo") and fallback:
            extra_fields["pseudo"] = fallback
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "ADMIN")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Le superutilisateur doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Le superutilisateur doit avoir is_superuser=True.")
        return self.create_user(email=email, password=password, **extra_fields)


class Utilisateur(AbstractUser):
    pseudo = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    telephone = models.CharField(max_length=30, unique=True, blank=True, null=True)
    date_naissance = models.DateField(blank=True, null=True)
    email_verifie = models.BooleanField(default=False)
    code_parrain = models.CharField(max_length=12, unique=True, blank=True)
    code_parent = models.CharField(max_length=12, blank=True, null=True)
    ville_origine = models.CharField(max_length=100, blank=True, default="")
    photo_profil = models.ImageField(upload_to="profils/", blank=True, null=True)
    photo_couverture = models.ImageField(upload_to="couvertures/", blank=True, null=True)
    role = models.CharField(
        max_length=20,
        choices=[("ADMIN", "Admin"), ("JOUEUR", "Joueur")],
        default="JOUEUR",
    )
    en_ligne = models.BooleanField(default=False)
    emp_fingerprint = models.CharField(max_length=128, blank=True, default="")
    derniere_ip = models.GenericIPAddressField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["pseudo"]
    objects = UtilisateurManager()

    class Meta:
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        if not self.code_parrain:
            self.code_parrain = generer_code_parrain()
        if not self.username:
            self.username = self.pseudo or (self.email or "").split("@")[0] or (self.telephone or "")
        super().save(*args, **kwargs)

    @property
    def stats(self):
        return {
            "parties": self.participations.count(),
            "victoires": self.participations.filter(score_final__gt=0, vainqueur=True).count(),
        }
