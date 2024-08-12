#!/bin/bash

# Load the Default Profile
. ~/.bash_profile

# Set the pipefail option so the "tee" commands do not mask errors
set -o pipefail

# Set-up misc. variables
PID=$$
PGM=`basename $0`
PGM_DIR=`dirname $0`
SCRIPT_USER=`whoami`
LOG_DIR="${PGM_DIR}/logs"
LOG_FILE=${LOG_DIR}/${PGM}_${PID}_`date +%m%d%y_%H%M%S`.log

echo -e "Script: ${0} was called with arguments: ${1} ${2} ${3}" | tee -a ${LOG_FILE}

cd ${PGM_DIR}
source ./venv/bin/activate

export PYTHONPATH=${PGM_DIR}

echo "PYTHONPATH=${PYTHONPATH}" | tee -a ${LOG_FILE}

python -m main --output-filename="${1}" --report-definition-filename="${2}" --query-parameters="${3}" | tee -a ${LOG_FILE}

PYTHON_RC=$?

echo -e "\nPython exit code: ${PYTHON_RC}" | tee -a ${LOG_FILE}

echo -e "\nStarting SQL*Plus - `date +"%D %r"`" | tee -a ${LOG_FILE}

sqlplus -SILENT /NOLOG << EOF # >> ${LOG_FILE} # uncomment this to save the sqlplus session's output to the log file - NOTE: this is NOT secure and should only be used for debugging!

WHENEVER OSERROR EXIT FAILURE ROLLBACK;
WHENEVER SQLERROR EXIT FAILURE ROLLBACK;

-- Connect with the REPORT_CONNECT_STRING environment variable...
CONNECT ${REPORT_CONNECT_STRING}

SHOW USER;

VARIABLE b_pdf_file_name VARCHAR2 (100);

DECLARE

BEGIN
   :b_pdf_file_name := '${1}';

   INSERT INTO pdf_report_files (pdf_file_name, pdf_blob)
   VALUES (:b_pdf_file_name, load_blob_from_file (p_dirname  => 'PDF_REPORT_OUTPUT_DIR'
                                                , p_filename => :b_pdf_file_name
                                                 )
          );
   COMMIT;
END;
/

EXIT;

EOF

# Record the SQL*Plus exit code...
rc=$?

echo -e "\nExited SQL*Plus with Return Code: ${rc} on `date +"%D %r"`" | tee -a ${LOG_FILE}

exit ${rc}

