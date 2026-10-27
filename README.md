# stephanelabat.fr

Site vitrine de Stéphane Labat, maçonnerie et rénovation. Jekyll, publié par GitHub Pages.

## Ajouter un chantier

1. **Déposer les photos** dans un nouveau dossier de
   `~/Documents/photos papa/_Tri par chantier/`, nommé `Chantier NN - Description`
   (par exemple `Chantier 08 - Muret en pierre`). Les numéros suivent l'ordre
   chronologique : le plus grand numéro est affiché en premier.

2. **Lancer le script** (la première fois, créer l'environnement Python) :

   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r scripts/requirements.txt
   .venv/bin/python scripts/import_photos.py --only 8
   ```

   Sans `--only`, tous les chantiers sont réimportés. Le script :
   - réencode chaque photo en WebP (1600, 800 et 600 px, qualité 80) à partir des
     seuls pixels : aucune donnée EXIF, GPS ou XMP n'arrive dans le dépôt, et il
     s'arrête en erreur si un fichier en contient encore ;
   - range les fichiers dans `assets/chantiers/chantier-08/` ;
   - crée `_chantiers/chantier-08-....md`, ou le complète sans toucher aux textes.

3. **Écrire le texte** dans `_chantiers/chantier-08-....md` :

   ```yaml
   title: Muret en pierre
   commune: Grasse                # la commune, jamais l'adresse
   type: clotures                 # renovation | construction | clotures | terrasses
   cover: chantier-08-12          # photo de couverture
   before: chantier-08-01         # paire avant/après, facultative
   after: chantier-08-12
   ```

   puis, sous le second `---`, 3 lignes : ce qui a été fait, avec quoi, en combien
   de temps. Les `alt` des photos peuvent être précisés dans la liste `photos`.

4. **Vérifier** que la date de chaque chantier est la bonne : le script la lit
   dans les photos, et la laisse vide quand les photos ont été réexportées le
   jour même.

5. **Commit, push** :

   ```sh
   git add assets/chantiers/chantier-08 _chantiers
   git commit -m "feat: add chantier 08"
   git push
   ```

   GitHub Pages republie le site en une à deux minutes.

Renommer le dossier source (par exemple pour y ajouter la commune) ne crée pas de
doublon : le script retrouve le chantier par son numéro.

## Aperçu local

```sh
docker run --rm -p 4000:4000 -v "$PWD":/site -w /site ruby:3.3 \
  sh -c "bundle install && bundle exec jekyll serve --host 0.0.0.0"
```

puis <http://localhost:4000>.

## Tests du script

```sh
.venv/bin/python -m pytest scripts
```

## Informations légales

Raison sociale, forme, SIRET, siège et capital sont dans `_data/site.yml`, et la
page `mentions-legales.html` les reprend.

## DNS

Chez le registrar, pour `stephanelabat.fr` :

| Type  | Nom | Valeur |
|-------|-----|--------|
| A     | @   | 185.199.108.153 |
| A     | @   | 185.199.109.153 |
| A     | @   | 185.199.110.153 |
| A     | @   | 185.199.111.153 |
| AAAA  | @   | 2606:50c0:8000::153 |
| AAAA  | @   | 2606:50c0:8001::153 |
| AAAA  | @   | 2606:50c0:8002::153 |
| AAAA  | @   | 2606:50c0:8003::153 |
| CNAME | www | romain7495.github.io. |

Puis, dans Settings → Pages : domaine `stephanelabat.fr` et « Enforce HTTPS ».
