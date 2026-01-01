#!/bin/bash

trap 'echo "Interrupted"; kill 0; exit 130' INT

uNames=`uname -s`
osName=${uNames: 0: 4}
if [ "$osName" == "Darw" ] # Darwin
then
    COMMAND="ghead"
elif [ "$osName" == "Linu" ] # Linux
then
    COMMAND="head"
fi

SCRIPT=$(readlink -f $0)
SCRIPT_PATH=$(dirname "${SCRIPT}")

# graph, tpch, lsqb
DATABASE=$1

INPUT_DIR=$2
INPUT_DIR_PATH="${SCRIPT_PATH}/${INPUT_DIR}"

DUCK_NUM=${3:-1}

NUM_THREADS=${4:-72}

declare -A DUCK_MAP=(
  [1]="./build/release/duckdb"
)

if [[ -z ${DUCK_MAP[$DUCK_NUM]} ]]; then
  echo "Usage: $0 <db> <dir> <duck_num> [threads]" >&2
  echo "duck_num: 1-5=original logic, 6=multi-statement handling" >&2
  exit 1
fi
DUCKDB_BIN=${DUCK_MAP[$DUCK_NUM]}

# Suffix function
function FileSuffix() {
    local filename="$1"
    if [ -n "$filename" ]; then
        echo "${filename##*.}"
    fi
}

function IsSuffix() {
    local filename="$1"
    if [ "$(FileSuffix ${filename})" = "sql" ]
    then
        return 0
    else 
        return 1
    fi
}

# Function to handle multi-statement SQL files (DUCK_NUM=6)
function ProcessMultiStatementSQL() {
    local query_file="$1"
    local submit_query_1="$2"
    local submit_query_2="$3"
    
    # Check if file contains CREATE statements
    local create_count=$(grep -c "^[[:space:]]*[Cc][Rr][Ee][Aa][Tt][Ee]" "$query_file")
    
    if [[ $create_count -gt 0 ]]; then
        echo "Multi-statement SQL detected: $create_count CREATE statements"
        
        # Split: all but last statement to setup file
        ${COMMAND} -n -1 "$query_file" > "$submit_query_1"
        
        # Wrap final SELECT in COPY statement
        echo "COPY (" > "$submit_query_2"
        tail -n 1 "$query_file" | sed 's/;//g' >> "$submit_query_2"
        echo ") TO '/dev/null' (DELIMITER ',');" >> "$submit_query_2"
        
        return 1  # Multi-statement file
    else
        echo "Single statement SQL detected"
        
        # Wrap entire query in COPY statement
        echo "COPY (" > "$submit_query_1"
        cat "$query_file" | sed 's/;//g' >> "$submit_query_1"
        echo ") TO '/dev/null' (DELIMITER ',');" >> "$submit_query_1"
        
        return 0  # Single statement file
    fi
}

for file in $(ls ${INPUT_DIR_PATH})
do
    IsSuffix ${file}
    ret=$?
    if [ $ret -eq 0 ]
    then
        filename="${file%.*}"
        LOG_FILE="${INPUT_DIR_PATH}/log_${filename}_${DUCK_NUM}.txt"
        TIME_FILE="${INPUT_DIR_PATH}/time_${filename}_${DUCK_NUM}.txt"
        rm -f $LOG_FILE $TIME_FILE
        touch $LOG_FILE $TIME_FILE
        QUERY="${INPUT_DIR_PATH}/${file}"
        RAN=$RANDOM
        
        echo "Start ${DUCKDB_BIN} Task at ${QUERY}"
        
        # Different handling based on DUCK_NUM
        if [[ $DUCK_NUM -eq 1 ]]; then
            # DUCK_NUM=6: Multi-statement handling with file separation
            SUBMIT_QUERY_1="${INPUT_DIR_PATH}/query_${RAN}_setup.sql"
            SUBMIT_QUERY_2="${INPUT_DIR_PATH}/query_${RAN}_exec.sql"
            rm -f "${SUBMIT_QUERY_1}" "${SUBMIT_QUERY_2}"
            touch "${SUBMIT_QUERY_1}" "${SUBMIT_QUERY_2}"
            
            # Process SQL file and determine execution strategy
            ProcessMultiStatementSQL "$QUERY" "$SUBMIT_QUERY_1" "$SUBMIT_QUERY_2"
            is_multi_statement=$?
            
            for ((current_task=1; current_task<=5; current_task++)); 
            do
                echo "Current Task: ${current_task}"
                
                if [[ $is_multi_statement -eq 1 ]]; then
                    # Multi-statement execution: setup + timed execution
                    timeout -s SIGKILL 2h ${DUCKDB_BIN} \
                        -c ".open ${DATABASE}_db" \
                        -c "SET threads TO ${NUM_THREADS};" \
                        -c ".timer off" \
                        -c ".read ${SUBMIT_QUERY_1}" \
                        -c ".read ${SUBMIT_QUERY_2}" \
                        -c ".timer on" \
                        -c ".read ${SUBMIT_QUERY_2}" \
                        2>&1 | tee -a "${LOG_FILE}" | tail -n 1 | awk '{print $5}' >> "${TIME_FILE}"
                else
                    # Single statement execution
                    timeout -s SIGKILL 2h ${DUCKDB_BIN} \
                        -c ".open ${DATABASE}_db" \
                        -c "SET threads TO ${NUM_THREADS};" \
                        -c ".timer off" \
                        -c ".read ${SUBMIT_QUERY_1}" \
                        -c ".timer on" \
                        -c ".read ${SUBMIT_QUERY_1}" \
                        2>&1 | tee -a "${LOG_FILE}" | tail -n 1 | awk '{print $5}' >> "${TIME_FILE}"
                fi
            done
            
            # Cleanup separated files
            rm -f "${SUBMIT_QUERY_1}" "${SUBMIT_QUERY_2}"
            
        else
            # DUCK_NUM=1-5: Original logic (wrap entire file in COPY)
            SUBMIT_QUERY="${INPUT_DIR_PATH}/query_${RAN}.sql"
            rm -f "${SUBMIT_QUERY}"
            touch "${SUBMIT_QUERY}"
            echo "COPY (" >> ${SUBMIT_QUERY}
            cat ${QUERY} >> ${SUBMIT_QUERY}
            echo ") TO '/dev/null' (DELIMITER ',');" >> ${SUBMIT_QUERY}
            
            for ((current_task=1; current_task<=5; current_task++)); 
            do
                echo "Current Task: ${current_task}"
                timeout -s SIGKILL 2h ${DUCKDB_BIN} \
                    -c ".open ${DATABASE}_db" \
                    -c "SET threads TO ${NUM_THREADS};" \
                    -c ".timer off" \
                    -c ".read ${SUBMIT_QUERY}" \
                    -c ".timer on" \
                    -c ".read ${SUBMIT_QUERY}" \
                    2>&1 | tee -a "${LOG_FILE}" | tail -n 1 | awk '{print $5}' >> "${TIME_FILE}"
            done
            
            # Cleanup single file
            rm -f "${SUBMIT_QUERY}"
        fi
        
        awk '{s+=$1} END{if(NR) print "AVG", s/NR}' "$TIME_FILE" >> "$TIME_FILE"
        echo "End DuckDB Task..."
    fi
done