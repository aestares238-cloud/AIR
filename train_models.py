"""
Train one Isolation Forest per AC unit from Supabase, store the models, thresholds and
learning curves back in Supabase.

Run it whenever you want fresh models (by hand, or as a nightly Render cron job).
You can also press "Train now" for a single AC on the Manage ACs page.

    python train_models.py                 # every AC that has data
    python train_models.py --unit AC2      # one AC (device code)
    python train_models.py --pct 3         # looser threshold: aim for ~3% false alarms
    python train_models.py --plot          # also save ml_learning.png (needs: pip install matplotlib)

Uses the same database connection as the app (SUPABASE_URL in .env or the environment).
"""
import argparse

from database import get_db_connection
from services import ml_per_ac as ml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", help="train only this ac_unit (device code)")
    ap.add_argument("--limit", type=int, default=20000, help="newest rows per unit to use")
    ap.add_argument("--pct", type=float, default=ml.DEFAULT_PCT, help="threshold percentile")
    ap.add_argument("--plot", action="store_true", help="also save a PNG of the learning curves")
    ap.add_argument("--out", default="ml_learning.png")
    args = ap.parse_args()

    conn = get_db_connection()
    ml.ensure_tables(conn)
    units = [args.unit] if args.unit else ml.fetch_units(conn)
    if not units:
        print("No ac_unit values found in data_gathered.")
        return

    curves = {}
    for unit in units:
        df = ml.fetch_unit_df(conn, unit, args.limit)
        bundle = ml.train_unit(df, pct=args.pct)
        if bundle is None:
            print(f"[{unit}] skipped: {len(df)} rows, need at least {ml.MIN_ROWS} usable rows")
            continue
        ml.save_bundle(conn, unit, bundle)
        curve = ml.learning_curve(df, pct=args.pct)
        ml.save_curve(conn, unit, curve, args.pct)   # feeds the Model Learning page
        curves[unit] = curve
        print(f"[{unit}] trained on {bundle['n_rows']} rows, threshold = {bundle['threshold']:.4f}")
    conn.close()

    if curves and args.plot:
        ml.plot_learning(curves, args.out, pct=args.pct)
        print(f"Learning graph saved to {args.out}")


if __name__ == "__main__":
    main()
