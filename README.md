# sku-scraper-walmart

## Stores input

Le fichier `input/stores.json` contient les magasins cibles.

## Validation rapide

Le script `scraper.py` lit `input/stores.json` puis boucle sur `store_id` et `store_slug` :

```bash
python3 scraper.py
```

## Runner local (Windows)

Pour contourner le blocage des IP datacenter sur GitHub Actions, vous pouvez lancer le scraping en local puis pousser automatiquement les snapshots.

```bash
pip install -r requirements.txt
playwright install chromium
python run_local_and_push.py
```

Le script `run_local_and_push.py` exécute :
1. `scripts/walmart_sku_store_check.py`
2. `git add snapshots`
3. `git commit -m "chore: update walmart snapshots (local)"`
4. `git push`
