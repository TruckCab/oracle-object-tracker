import sys
import argparse
import logging
from utils import convert_key_value_string_to_dict
from classes.pdf_report import PDFReport


# Constants
REPORT_DEFINITION_PATH: str = "./report_definitions"
PDF_TEMPLATE_PATH: str = "./source_pdfs"

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger()
logger.setLevel(level=logging.INFO)


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--output-filename",
                            type=str,
                            required=True,
                            help="Enter the name of the report output PDF filename to be created in the ./output_files directory"
                            )
        parser.add_argument("--report-definition-filename",
                            type=str,
                            required=True,
                            help="Enter the name of the report definition YAML file in the ./report_definitions directory"
                            )
        parser.add_argument("--query-parameters",
                            type=str,
                            required=False,
                            help="Enter a comma-delimited list of key=value pair args.  Example: 'year=2021,color=blue'"
                            )
        parser.add_argument('--run-preprocessing', action='store_true')
        parser.add_argument('--no-run-preprocessing', dest='run_preprocessing', action='store_false')
        parser.set_defaults(run_preprocessing=True)

        args = parser.parse_args()
        logging.info(msg=(f"Module {__file__} was called with arguments:\n"
                          f"--output-filename = '{args.output_filename}'\n"
                          f"--report-definition-filename = '{args.report_definition_filename}'\n"
                          f"--query-parameters = '{args.query_parameters}'\n"
                          f"--run-preprocessing = {args.run_preprocessing}"
                          )
                     )

        pdf_report = PDFReport(output_filename=args.output_filename,
                               report_definition_filename=args.report_definition_filename,
                               query_parameter_dict=convert_key_value_string_to_dict(input_str=args.query_parameters.strip('"')),
                               run_preprocessing=args.run_preprocessing
                               )
        pdf_report.generate_pdf()
    except Exception as e:
        logger.error(msg=str(e))
        raise
    else:
        logger.info(msg=f"Module: {__file__} ran successfully.")
