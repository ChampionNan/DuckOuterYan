import csv
import random
import os

# ==========================================
# CONFIGURATION
# ==========================================
TOTAL_IDS = 1_000_000
OUTPUT_DIR = "rstk_data"

def generate_csvs():
    # 1. Setup Output Directory
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

    # 2. File Handles
    tables = ['R', 'S', 'T', 'K']
    files = {}
    writers = {}

    try:
        # Open all files
        for t in tables:
            f = open(f"{OUTPUT_DIR}/{t}.csv", 'w', newline='')
            files[t] = f
            writers[t] = csv.writer(f)
            writers[t].writerow(['src', 'dst'])

        print(f"Generating {TOTAL_IDS} IDs with messy join patterns...")

        # 3. Data Generation Strategy:
        # - Create OVERLAPPING but INCOMPLETE chains to force NULL padding
        # - Use different src/dst patterns to break join paths
        # - Add orphan rows (rows that match nothing)
        
        for i in range(1, TOTAL_IDS + 1):
            
            # Force first 30 IDs to cover all edge cases
            if i <= 30:
                signature = i % 16
            else:
                signature = random.randint(0, 15)

            # Strategy 1: BROKEN CHAINS (30% of data)
            # Create src/dst mismatches to force NULL padding in outer joins
            if i % 10 < 3:
                # R points to nowhere
                if signature & 1:
                    writers['R'].writerow([i, i + 1000000])  # dst won't match any src
                
                # S has orphan src (no R pointing to it)
                if signature & 2:
                    writers['S'].writerow([i + 2000000, i])
                
                # T exists but S.dst != T.src
                if signature & 4:
                    writers['T'].writerow([i + 3000000, i])
                
                # K completely isolated
                if signature & 8:
                    writers['K'].writerow([i + 4000000, i + 5000000])
            
            # Strategy 2: PARTIAL CHAINS (40% of data)
            # Some tables exist, others missing - perfect for LEFT/RIGHT OUTER JOIN
            elif i % 10 < 7:
                # R -> S chain works, but T is missing
                if signature & 1:
                    writers['R'].writerow([i, i + 100])
                
                if signature & 2:
                    writers['S'].writerow([i + 100, i + 200])
                
                # Randomly skip T or K to create NULL padding
                if (signature & 4) and random.random() > 0.5:
                    writers['T'].writerow([i + 200, i + 300])
                
                if (signature & 8) and random.random() > 0.6:
                    writers['K'].writerow([i + 300, i + 400])
            
            # Strategy 3: COMPLETE CHAINS (20% of data)
            # Full joinable chains for baseline
            elif i % 10 < 9:
                if signature & 1:
                    writers['R'].writerow([i, i])
                if signature & 2:
                    writers['S'].writerow([i, i])
                if signature & 4:
                    writers['T'].writerow([i, i])
                if signature & 8:
                    writers['K'].writerow([i, i])
            
            # Strategy 4: DUPLICATE KEYS (10% of data)
            # Multiple rows with same src/dst to test join multiplicity
            else:
                base_id = i // 100 * 100  # Group into buckets
                
                if signature & 1:
                    writers['R'].writerow([base_id, base_id + 50])
                    writers['R'].writerow([base_id, base_id + 50])  # Duplicate
                
                if signature & 2:
                    writers['S'].writerow([base_id + 50, base_id + 100])
                
                if signature & 4:
                    writers['T'].writerow([base_id + 100, base_id + 150])
                    writers['T'].writerow([base_id + 100, base_id + 150])  # Duplicate

    finally:
        for f in files.values():
            f.close()

    print(f"\nData Generation Complete!")
    print(f"Edge Cases Created:")
    print(f"  ✓ Broken chains (30%): R.dst doesn't match S.src → NULL padding")
    print(f"  ✓ Partial chains (40%): Missing T or K → LEFT/RIGHT OUTER differences")
    print(f"  ✓ Complete chains (20%): Full joins work")
    print(f"  ✓ Duplicates (10%): Tests join multiplicity")
    print(f"  ✓ Orphan rows: Rows that match nothing in other tables")
    print(f"\nFiles saved to '{OUTPUT_DIR}/'")

if __name__ == "__main__":
    generate_csvs()