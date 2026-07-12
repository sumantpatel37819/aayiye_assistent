import os, sys
sys.path.append(os.getcwd())
try:
    from index_main import extract_enrich_params
    print("Result:", extract_enrich_params("bihar ke saare places fill karo"))
except Exception as e:
    print("Error:", e)
