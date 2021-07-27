from ftw import ruleset, logchecker, testrunner
import datetime
import pytest
import sys
import re
import os


def test_crs(ruleset, test, logchecker_obj, config):
    runner = testrunner.TestRunner()
    if test.annotation and 'skip' in test.annotation:
        skips = skip_test(test.annotation['skip'], config)
        if skips.is_true:
            pytest.skip(skips.reason if skips.reason else 'Skipped due to the skip condition.')
    for stage in test.stages:
        runner.run_stage(stage, logchecker_obj)


def skip_test(skip_annotation, config):
    for config_param in skip_annotation.keys():
        skips = Condition(skip_annotation[config_param]).eval(config[config_param])
        if skips.is_true:
            return skips
    return ConditionResult(False, None)


class Condition:
    def __init__(self, condition):
        self.op = None
        self.val = None
        self.reason = None
        for op, val in condition.items():
            if op == 'reason':
                self.reason = val
                continue
            if self.op is not None:
                raise Exception('More than one operator in a single operator.')
            self.op = op
            self.val = val

    def eval(self, val):
        if self.op == 'in':
            return ConditionResult(val in self.val, self.reason)
        elif self.op == 'not-in':
            return ConditionResult(val not in self.val, self.reason)
        elif self.op == 'is':
            return ConditionResult(val == self.val, self.reason)
        elif self.op == 'is-not':
            return ConditionResult(val != self.val, self.reason)
        elif self.op == 'or':
            for condition in self.val or []:
                result = Condition(condition).eval(val)
                if result.is_true:
                    return ConditionResult(True, self.reason or result.reason)
            return ConditionResult(False, self.reason)
        else:
            raise Exception(f'Invalid operator: {self.op}')


class ConditionResult:
    def __init__(self, is_true, reason):
        self.is_true = is_true
        self.reason = reason


class FooLogChecker(logchecker.LogChecker):
    def __init__(self, config):
        super(FooLogChecker, self).__init__()
        self.log_location = config['log_location_linux']
        self.log_date_regex = config['log_date_regex']
        self.log_date_format = config['log_date_format']

    def reverse_readline(self, filename):
        with open(filename) as f:
            f.seek(0, os.SEEK_END)
            position = f.tell()
            line = ''
            while position >= 0:
                f.seek(position)
                next_char = f.read(1)
                if next_char == "\n":
                    yield line[::-1]
                    line = ''
                else:
                    line += next_char
                position -= 1
            yield line[::-1]

    def get_logs(self):
        pattern = re.compile(r'%s' % self.log_date_regex)
        our_logs = []
        for lline in self.reverse_readline(self.log_location):
            # Extract dates from each line
            match = re.match(pattern, lline)
            if match:
                log_date = match.group(1)
                log_date = datetime.datetime.strptime(
                    log_date, self.log_date_format)
                # NGINX doesn't give us microsecond level by detail, round down.
                if "%f" not in self.log_date_format:
                    ftw_start = self.start.replace(microsecond=0)
                    ftw_end = self.end.replace(microsecond=0)
                else:
                    ftw_start = self.start
                    ftw_end = self.end
                if log_date <= ftw_end and log_date >= ftw_start:
                    our_logs.append(lline)
                # If our log is from before FTW started stop
                if log_date < ftw_start:
                    break
        return our_logs


@pytest.fixture(scope='session')
def logchecker_obj(config):
    return FooLogChecker(config)
