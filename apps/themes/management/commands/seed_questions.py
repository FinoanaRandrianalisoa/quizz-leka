from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.themes.models import Theme, Question, Reponse


DONNEES = {
    "Culture Générale": [
        ("Quelle est la capitale de Madagascar ?", ["Antananarivo", "Toamasina", "Mahajanga", "Fianarantsoa"], 0),
        ("Combien de continents y a-t-il ?", ["5", "6", "7", "8"], 2),
        ("Quelle est la monnaie officielle de Madagascar ?", ["Franc malagasy", "Ariary", "Rupee", "Shilling"], 1),
        ("Quel océan borde Madagascar ?", ["Atlantique", "Pacifique", "Indien", "Arctique"], 2),
        ("Madagascar est la ... plus grande île du monde.", ["1re", "2e", "4e", "6e"], 2),
        ("Quel animal emblématique est associé à Madagascar ?", ["Kangourou", "Lémurien", "Panda", "Jaguar"], 1),
        ("Comment dit-on « bonjour » en malgache le matin ?", ["Veloma", "Misaotra", "Salama", "Azafady"], 2),
        ("Quel est le code ISO du pays ?", ["MDG", "MAD", "MADA", "MGR"], 0),
        ("Quelle est la 2e ville de Madagascar ?", ["Toamasina", "Antsirabe", "Mahajanga", "Toliara"], 0),
        ("Quel plat est souvent considéré comme national ?", ["Romazava", "Sushi", "Couscous", "Paella"], 0),
    ],
    "Histoire Malagasy": [
        ("En quelle année Madagascar obtient-elle son indépendance ?", ["1958", "1960", "1962", "1965"], 1),
        ("Qui fut le premier président de la République malgache ?", ["Didier Ratsiraka", "Philibert Tsiranana", "Marc Ravalomanana", "Albert Zafy"], 1),
        ("Quel royaume a unifié une grande partie de l'île au XIXe siècle ?", ["Sakalava", "Betsileo", "Merina", "Antandroy"], 2),
        ("Andrianampoinimerina régnait depuis quelle colline ?", ["Ambohimanga", "Antsirabe", "Fianarantsoa", "Toamasina"], 0),
        ("Quel traité a marqué la colonisation française ?", ["Traité de Tamatave", "Traité de Versailles", "Traité d'Antananarivo", "Traité de Berlin"], 0),
        ("Ranavalona Ire était une reine de quel siècle ?", ["XVIIe", "XVIIIe", "XIXe", "XXe"], 2),
        ("Quel événement a lieu le 26 juin ?", ["Fête nationale", "Nouvel an", "Fête des morts", "Independence Day US"], 0),
        ("La période coloniale française a duré principalement de...", ["1810-1860", "1896-1960", "1960-1975", "1700-1750"], 1),
        ("Quel nom porte le palais royal d'Antananarivo ?", ["Rova", "Ilafy", "Ambohimalaza", "Manjakamiadana uniquement"], 0),
        ("Le 29 mars 1947 est associé à...", ["L'indépendance", "L'insurrection", "La première élection", "La fondation d'Antananarivo"], 1),
    ],
    "Géographie": [
        ("Quel est le plus haut sommet de Madagascar ?", ["Tsaratanana", "Maromokotro", "Andringitra", "Ankaratra"], 1),
        ("Combien de régions administratives compte Madagascar ?", ["6", "12", "22", "23"], 2),
        ("Toliara se trouve dans quelle partie de l'île ?", ["Nord", "Est", "Sud-Ouest", "Centre"], 2),
        ("Quel parc est célèbre pour ses baobabs ?", ["Andasibe", "Isalo", "Kirindy / Allée des Baobabs", "Ranomafana"], 2),
        ("Antsiranana est aussi appelée...", ["Diego-Suarez", "Fort-Dauphin", "Majunga", "Tamatave"], 0),
        ("Le Canal du Mozambique sépare Madagascar de...", ["l'Inde", "l'Afrique", "l'Australie", "Sri Lanka"], 1),
        ("Quelle ville est un grand port de l'Est ?", ["Mahajanga", "Toamasina", "Toliara", "Antsirabe"], 1),
        ("Le massif de l'Isalo est connu pour...", ["ses glaciers", "ses canyons", "ses volcans actifs", "ses fjords"], 1),
        ("Nosy Be se situe au...", ["Sud", "Nord-Ouest", "Est", "Centre"], 1),
        ("Le lac Alaotra est le plus grand lac...", ["salé", "d'eau douce du pays", "artificiel d'Afrique", "volcanique"], 1),
    ],
    "Traditions": [
        ("Le famadihana est...", ["un rite de retournement des morts", "une danse de mariage", "un jeu d'enfants", "une fête de la moisson uniquement"], 0),
        ("Le kabary est...", ["un discours oratoire", "un instrument", "un plat", "un vêtement"], 0),
        ("Le lamba est...", ["une pièce de tissu traditionnelle", "un chapeau", "une pirogue", "un tambour"], 0),
        ("Le hiragasy est...", ["un art populaire de spectacle", "un type de riz", "un clan royal", "une monnaie ancienne"], 0),
        ("Le fady désigne...", ["un interdit culturel", "un salut", "un marché", "un roi"], 0),
        ("Le tromba est lié à...", ["la possession spirituelle", "la pêche", "l'école", "le football"], 0),
        ("Le tsiky est souvent...", ["un sourire / rire", "un serment", "un deuil", "un impôt"], 0),
        ("Le vary amin'anana est...", ["un plat de riz aux brèdes", "un alcool", "un rite funéraire", "un instrument"], 0),
        ("Le moramora évoque...", ["prendre son temps", "se battre", "voyager loin", "compter l'argent"], 0),
        ("Le fihavanana désigne...", ["le lien de solidarité", "la guerre", "l'impôt", "la chasse"], 0),
    ],
    "Ohabolana": [
        ("« Ny fahamarinana no mampanjaka » signifie...", ["La vérité fait régner", "L'argent domine", "Le travail récompense", "La patience gagne"], 0),
        ("« Ny adala no tsy mianatra » insiste sur...", ["l'apprentissage", "la guerre", "la danse", "la pêche"], 0),
        ("Un ohabolana est...", ["un proverbe malgache", "une danse", "un roi", "un oiseau"], 0),
        ("« Aleo very tsikalolona toy izay very tsikaoloana » parle de...", ["relations humaines vs biens", "la mer", "les lémuriens", "le riz"], 0),
        ("Les ohabolana transmettent surtout...", ["la sagesse populaire", "des recettes secrètes", "des codes militaires", "des dates d'impôts"], 0),
        ("« Ny tovolahy tsy miasa tsy hanina » valorise...", ["le travail", "le sommeil", "la chasse", "le silence"], 0),
        ("Un hainteny est plutôt...", ["un poème / joute verbale", "un tambour", "un marché", "un palais"], 0),
        ("« Izay tsy mahay miteny tsy mahay mifankatia » lie parole et...", ["entente", "richesse", "voyage", "guerre"], 0),
        ("Les proverbes malgaches sont souvent dits en...", ["kabary", "anglais", "latin", "swahili uniquement"], 0),
        ("« Ny rano tsy tokony hofafazana afo » met en garde contre...", ["la contradiction / l'inutile", "la cuisine", "la pluie", "le froid"], 0),
    ],
    "Sport": [
        ("Quel sport est le plus populaire à Madagascar ?", ["Basket", "Football", "Rugby", "Tennis"], 1),
        ("Les Barea sont l'équipe nationale de...", ["basket", "football", "volleyball", "handball"], 1),
        ("Le rugby à Madagascar est particulièrement fort à...", ["Antananarivo et Fianarantsoa", "Paris", "Nairobi", "Pékin"], 0),
        ("La CAN désigne...", ["Coupe d'Afrique des Nations", "Club Athlétique National", "Coupe Antananarivo", "Comité des Arts"], 0),
        ("Le moraingy est...", ["un art martial traditionnel", "un sprint", "un plongeon", "un sport équestre européen"], 0),
        ("Le stade municipal de Mahamasina se trouve à...", ["Toamasina", "Antananarivo", "Toliara", "Mahajanga"], 1),
        ("Le pétanque est très pratiqué notamment...", ["en ville", "uniquement à la mer", "dans les forêts", "au pôle sud"], 0),
        ("Qui organise les Jeux des Îles de l'océan Indien ?", ["la CIA", "la CIOI / CIO", "la FIFA seule", "l'ONU"], 1),
        ("Le fanorona est...", ["un jeu de stratégie malgache", "un sport nautique", "un marathon", "un lancer de poids"], 0),
        ("Un match se joue souvent en...", ["deux mi-temps", "cinq sets obligatoires", "innings", "chukkas"], 0),
    ],
    "Sciences": [
        ("Quelle est la formule chimique de l'eau ?", ["CO2", "H2O", "O2", "NaCl"], 1),
        ("La Terre tourne autour du...", ["Lune", "Soleil", "Mars", "Jupiter"], 1),
        ("Combien y a-t-il de planètes dans le système solaire ?", ["7", "8", "9", "10"], 1),
        ("Le baobab stocke surtout de l'eau dans...", ["ses feuilles", "son tronc", "ses fleurs", "ses racines uniquement"], 1),
        ("Un lémurien est un...", ["primate", "félin", "oiseau", "reptile"], 0),
        ("La photosynthèse a lieu surtout dans...", ["les racines", "les feuilles", "l'écorce morte", "les graines sèches"], 1),
        ("L'unité de force est le...", ["watt", "newton", "pascal", "volt"], 1),
        ("Le fossile évoque...", ["un reste d'organisme ancien", "un nuage", "un métal pur", "un gaz"], 0),
        ("Madagascar est un hotspot de...", ["biodiversité", "pétrole mondial", "glace polaire", "désert saharien"], 0),
        ("Le fossa est un...", ["carnivore endémique", "poisson d'eau douce", "insecte", "amphibien marin"], 0),
    ],
    "Musique": [
        ("Qui est surnommé « Rossy » ?", ["Chanteur malgache", "Acteur hollywoodien", "Footballeur brésilien", "Chef cuisinier"], 0),
        ("Le salegy est un rythme d'origine...", ["Nord de Madagascar", "Ouest uniquement", "Centre", "Sud extrême"], 0),
        ("Le valiha est...", ["un instrument à cordes", "un tambour royal", "une flûte européenne", "un piano"], 0),
        ("Le tsapiky est associé surtout au...", ["Sud", "Nord", "Est côtier uniquement", "Hauts plateaux uniquement"], 0),
        ("Le hira gasy mêle musique et...", ["théâtre populaire", "opéra italien", "rap américain", "jazz de La Nouvelle-Orléans uniquement"], 0),
        ("Un kabosy est...", ["une petite guitare", "une trompette", "un xylophone", "une harpe celtique"], 0),
        ("Le kiloloka évoque...", ["un rythme / danse", "un palais", "un impôt", "un volcan"], 0),
        ("Le vakodrazana désigne plutôt...", ["le patrimoine ancestral (dont musical)", "un club de foot", "une monnaie", "un port"], 0),
        ("Un concert live se dit souvent...", ["hira velona", "hira maty", "kabary foana", "lamba fotsy"], 0),
        ("Le sodina est proche d'une...", ["flûte", "batterie", "contrebasse", "accordéon"], 0),
    ],
}

class Command(BaseCommand):
    help = "Importe en masse les questions de base par thème."

    def handle(self, *args, **options):
        for theme_nom, questions in DONNEES.items():
            theme, _ = Theme.objects.get_or_create(
                nom=theme_nom,
                defaults={
                    "slug": slugify(theme_nom),
                    "description": f"Questions de {theme_nom}",
                    "icone": slugify(theme_nom),
                },
            )
            for texte, reponses, correct_idx in questions:
                if Question.objects.filter(theme=theme, texte=texte).exists():
                    continue
                question = Question.objects.create(theme=theme, texte=texte, validee=True)
                for i, r in enumerate(reponses):
                    Reponse.objects.create(question=question, texte=r, est_correcte=(i == correct_idx))
            self.stdout.write(self.style.SUCCESS(f"Thème '{theme_nom}' : {len(questions)} questions"))
