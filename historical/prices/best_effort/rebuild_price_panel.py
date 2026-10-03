"""One-command reproducible price pipeline; cached downloaded files are reused.
Run this file only after the independent build_actions.py action file is available.
The provisional strategy runner consumes the final prices_usd.csv.gz.
"""
import build_prices
import refine_prices
import finalize_prices
import primary_price_repairs
import final_price_adjustments
import apply_ticker_continuations
if __name__=='__main__':
    build_prices.download()
    build_prices.build()
    refine_prices.main()
    finalize_prices.main()
    primary_price_repairs.main()
    final_price_adjustments.main()
    apply_ticker_continuations.main()
    import runpy
    runpy.run_path(str(build_prices.P / 'audit_action_boundaries.py'), run_name='__main__')
