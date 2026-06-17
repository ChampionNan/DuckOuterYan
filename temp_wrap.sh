bash auto_test/experiment_onoff.sh --rscale 100000
./experiment_semijoin.sh -N 1000000 -D 5000000 -p 0.8 -n 5 --min-secs 300 -t 900 --kill-after 1200
bash auto_test/compare_equal_batch.sh all > compare_equal_batch_results.txt 2>&1
