#!/usr/bin/env python
import os
import shutil
import subprocess

import yaml
from ebi_eva_common_pyutils import command_utils
from ebi_eva_common_pyutils.config import cfg

from eva_submission.eload_submission import Eload
from eva_submission.eload_utils import resolve_single_file_path
from eva_submission.samples_checker import compare_spreadsheet_and_vcf


class EloadValidation(Eload):

    def validate(self):
        # (Re-)Initialise the config file output
        self.eload_cfg['validation'] = {
            'validation_date': self.now,
            'assembly_check': {},
            'vcf_check': {},
            'sample_check': {},
            'valid': {}
        }
        self._validate_spreadsheet()
        output_dir = self._run_validation_workflow()
        self._collect_validation_worklflow_results(output_dir)
        shutil.rmtree(output_dir)

        if all([self.eload_cfg['validation'][key]['pass'] for key in ['vcf_check', 'assembly_check', 'sample_check']]):
            self.eload_cfg.set('validation', 'valid', 'vcf_files', value=self.eload_cfg['submission']['vcf_files'])
            self.eload_cfg.set('validation', 'valid', 'metadata_spreadsheet', value=self.eload_cfg['submission']['metadata_spreadsheet'])

    def _validate_spreadsheet(self):
        overall_differences, results_per_analysis_alias = compare_spreadsheet_and_vcf(
            eva_files_sheet=self.eload_cfg['submission']['metadata_spreadsheet'],
            vcf_dir=self._get_dir('vcf'),
            expected_vcf_files=self.eload_cfg['submission']['vcf_files']
        )
        for analysis_alias in results_per_analysis_alias:
            has_difference, diff_submitted_file_submission, diff_submission_submitted_file = results_per_analysis_alias[analysis_alias]

            self.eload_cfg.set('validation', 'sample_check', 'analysis', str(analysis_alias), value={
                'difference_exists': has_difference,
                'in_VCF_not_in_metadata': diff_submitted_file_submission,
                'in_metadata_not_in_VCF': diff_submission_submitted_file
            })
        self.eload_cfg.set('validation', 'sample_check', 'pass', value=not overall_differences)

    def parse_assembly_check_log(self, assembly_check_log):
        error_list = []
        nb_error = 0
        match = total = None
        with open(assembly_check_log) as open_file:
            for line in open_file:
                if line.startswith('[error]'):
                    nb_error += 1
                    if nb_error < 11:
                        error_list.append(line.strip()[len('[error]'):])
                elif line.startswith('[info] Number of matches:'):
                    match, total = line.strip()[len('[info] Number of matches: '):].split('/')
                    match = int(match)
                    total = int(total)
        return error_list, nb_error, match, total

    def parse_vcf_check_report(self, vcf_check_report):
        valid = True
        error_list = []
        warning_count = error_count = 0
        with open(vcf_check_report) as open_file:
            for line in open_file:
                if 'warning' in line:
                    warning_count = 1
                elif line.startswith('According to the VCF specification'):
                    if 'not' in line:
                        valid = False
                else:
                    error_count += 1
                    if error_count < 11:
                        error_list.append(line.strip())
        return valid, error_list, error_count, warning_count

    def _run_validation_workflow(self):
        output_dir = self.create_temp_output_directory()
        validation_config = {
            'metadata_file': self.eload_cfg.query('submission', 'metadata_spreadsheet'),
            'vcf_files': self.eload_cfg.query('submission', 'vcf_files'),
            'reference_fasta': self.eload_cfg.query('submission', 'assembly_fasta'),
            'reference_report': self.eload_cfg.query('submission', 'assembly_report'),
            'output_dir': output_dir,
            'executable': cfg['executable']
        }
        # run the validation
        validation_confg_file = os.path.join(self.eload_dir, 'validation_confg_file.yaml')
        with open(validation_confg_file, 'w') as open_file:
            yaml.safe_dump(validation_config, open_file)
        validation_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'nextflow', 'validation.nf')
        try:
            command_utils.run_command_with_output(
                'Start Nextflow Validation process',
                ' '.join((
                    cfg['executable']['nextflow'], validation_script,
                    '-params-file', validation_confg_file,
                    '-work-dir', output_dir
                ))
            )
        except subprocess.CalledProcessError:
            self.error('Nextflow pipeline failed: results might not be complete')
        return output_dir

    def _move_file(self, source, dest):
        if source:
            self.debug('Rename %s to %s', source, dest)
            os.rename(source, dest)
            return dest
        else:
            return None

    def _collect_validation_worklflow_results(self, output_dir):
        # Collect information from the output and summarise in the config
        total_error = 0
        # detect output files for vcf check
        for vcf_file in self.eload_cfg.query('submission', 'vcf_files'):
            vcf_name = os.path.basename(vcf_file)

            tmp_vcf_check_log = resolve_single_file_path(
                os.path.join(output_dir, 'vcf_format', vcf_name + '.vcf_format.log')
            )
            tmp_vcf_check_text_report = resolve_single_file_path(
                os.path.join(output_dir, 'vcf_format', vcf_name + '.*.txt')
            )
            tmp_vcf_check_db_report = resolve_single_file_path(
                os.path.join(output_dir, 'vcf_format', vcf_name + '.*.db')
            )

            # move the output files
            vcf_check_log = self._move_file(
                tmp_vcf_check_log,
                os.path.join(self._get_dir('vcf_check'), vcf_name + '.vcf_format.log')
            )
            vcf_check_text_report = self._move_file(
                tmp_vcf_check_text_report,
                os.path.join(self._get_dir('vcf_check'), vcf_name + '.vcf_validator.txt')
            )
            vcf_check_db_report = self._move_file(
                tmp_vcf_check_db_report,
                os.path.join(self._get_dir('vcf_check'), vcf_name + '.vcf_validator.db')
            )
            if vcf_check_log and vcf_check_text_report and vcf_check_db_report:
                valid, error_list, error_count, warning_count = self.parse_vcf_check_report(vcf_check_text_report)
            else:
                valid, error_list, error_count, warning_count = (False, 'Process failed', 1, 0)
            total_error += error_count

            self.eload_cfg.set('validation', 'vcf_check', 'files', vcf_name, value={
                'error_list': error_list, 'nb_error': error_count, 'nb_warning': warning_count,
                'vcf_check_log': vcf_check_log, 'vcf_check_text_report': vcf_check_text_report,
                'vcf_check_db_report': vcf_check_db_report
            })
        self.eload_cfg.set('validation', 'vcf_check', 'pass', value=total_error == 0)

        # detect output files for assembly check
        total_error = 0
        for vcf_file in self.eload_cfg.query('submission', 'vcf_files'):
            vcf_name = os.path.basename(vcf_file)

            tmp_assembly_check_log = resolve_single_file_path(
                os.path.join(output_dir, 'assembly_check',  vcf_name + '.assembly_check.log')
            )
            tmp_assembly_check_valid_vcf = resolve_single_file_path(
                os.path.join(output_dir, 'assembly_check', vcf_name + '.valid_assembly_report*')
            )
            tmp_assembly_check_text_report = resolve_single_file_path(
                os.path.join(output_dir, 'assembly_check', vcf_name + '*text_assembly_report*')
            )

            # move the output files
            assembly_check_log = self._move_file(
                tmp_assembly_check_log,
                os.path.join(self._get_dir('assembly_check'), vcf_name + '.assembly_check.log')
            )
            assembly_check_valid_vcf = self._move_file(
                tmp_assembly_check_valid_vcf,
                os.path.join(self._get_dir('assembly_check'), vcf_name + '.valid_assembly_report.txt')
            )
            assembly_check_text_report = self._move_file(
                tmp_assembly_check_text_report,
                os.path.join(self._get_dir('assembly_check'), vcf_name + '.text_assembly_report.txt')
            )
            if assembly_check_log and assembly_check_valid_vcf and assembly_check_text_report:
                error_list, nb_error, match, total = self.parse_assembly_check_log(assembly_check_log)
            else:
                error_list, nb_error, match, total = (['Process failed'], 1, 0, 0)
            total_error += nb_error
            self.eload_cfg.set('validation', 'assembly_check', 'files', vcf_name, value={
                'error_list': error_list, 'nb_error': nb_error, 'ref_match': match, 'nb_variant': total,
                'assembly_check_log': assembly_check_log, 'assembly_check_valid_vcf': assembly_check_valid_vcf,
                'assembly_check_text_report': assembly_check_text_report
            })
        self.eload_cfg.set('validation', 'assembly_check', 'pass', value=total_error == 0)

    def _vcf_check_report(self):
        reports = []
        for vcf_file in self.eload_cfg.query('validation', 'vcf_check', 'files'):
            results = self.eload_cfg.query('validation', 'vcf_check', 'files', vcf_file)
            report_data = {
                'vcf_file': vcf_file,
                'pass': 'PASS' if results.get('nb_error') == 0 else 'FAIL',
                '10_error_list': '\n'.join(results['error_list'])
            }
            report_data.update(results)
            reports.append("""  * {vcf_file}: {pass}
    - number of error: {nb_error}
    - number of warning: {nb_warning}
    - first 10 errors: {10_error_list}
    - see report for detail: {vcf_check_text_report}
""".format(**report_data))
        return '\n'.join(reports)

    def _assembly_check_report(self):
        reports = []
        for vcf_file in self.eload_cfg.query('validation', 'assembly_check', 'files'):
            results = self.eload_cfg.query('validation', 'assembly_check', 'files', vcf_file)
            report_data = {
                'vcf_file': vcf_file,
                'pass': 'PASS' if results.get('nb_error') == 0 else 'FAIL',
                '10_error_list': '\n'.join(results['error_list'])
            }
            report_data.update(results)
            reports.append("""  * {vcf_file}: {pass}
    - number of error: {nb_error}
    - match results: {ref_match}/{nb_variant}
    - first 10 errors: {10_error_list}
    - see report for detail: {assembly_check_text_report}
""".format(**report_data))
        return '\n'.join(reports)

    def _sample_check_report(self):
        reports = []
        for analysis_alias in self.eload_cfg.query('validation', 'sample_check', 'analysis'):
            results = self.eload_cfg.query('validation', 'sample_check', 'analysis', analysis_alias)
            report_data = {
                'analysis_alias': analysis_alias,
                'pass': 'FAIL' if results.get('difference_exists') else 'PASS',
                'in_VCF_not_in_metadata': ', '.join(results['in_VCF_not_in_metadata']),
                'in_metadata_not_in_VCF': ', '.join(results['in_metadata_not_in_VCF'])
            }
            reports.append("""  * {analysis_alias}: {pass}
    - Samples that appear in the VCF but not in the Metadata sheet:: {in_VCF_not_in_metadata}
    - Samples that appear in the Metadata sheet but not in the VCF file(s): {in_metadata_not_in_VCF}
""".format(**report_data))
        return '\n'.join(reports)

    def report(self):
        """Collect information from the config and write the report."""

        report_data = {
            'validation_date': self.eload_cfg.query('validation', 'validation_date'),
            'vcf_check': 'PASS' if self.eload_cfg.query('validation', 'vcf_check', 'pass') else 'FAIL',
            'assembly_check': 'PASS' if self.eload_cfg.query('validation', 'assembly_check', 'pass') else 'FAIL',
            'sample_check': 'PASS' if self.eload_cfg.query('validation', 'sample_check', 'pass') else 'FAIL',
            'vcf_check_report': self._vcf_check_report(),
            'assembly_check_report': self._assembly_check_report(),
            'sample_check_report': self._sample_check_report()
        }

        report = """Validation performed on {validation_date}
VCF check: {vcf_check}
Assembly check: {assembly_check}
Sample names check: {sample_check}
----------------------------------

VCF check:
{vcf_check_report}
----------------------------------

Assembly check:
{assembly_check_report}
----------------------------------

Sample names check:
{sample_check_report}
----------------------------------
"""
        print(report.format(**report_data))


