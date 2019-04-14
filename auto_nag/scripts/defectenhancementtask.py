# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from auto_nag import logger
from auto_nag.bugbug_utils import BugbugScript
from bugbug.models.defect_enhancement_task import DefectEnhancementTaskModel


class DefectEnhancementTask(BugbugScript):
    def __init__(self):
        super().__init__()
        self.model = DefectEnhancementTaskModel.load(self.retrieve_model())

    def description(self):
        return '[Using ML] Check that the bug type is the same as predicted by bugbug'

    def columns(self):
        return ['id', 'summary', 'type', 'bugbug_type', 'confidence']

    def sort_columns(self):
        def _sort_columns(p):
            if p[2] == 'defect':  # defect -> non-defect is what we plan to autofix, so we show it first in the email.
                prio = 0
            elif p[3] == 'defect':  # non-defect -> defect has more priority than the rest, as 'enhancement' and 'task' can be often confused.
                prio = 1
            else:
                prio = 2

            # Then, we sort by confidence and ID.
            return (prio, -p[4], -p[0])

        return _sort_columns

    def get_bz_params(self, date):
        start_date, _ = self.get_dates(date)

        reporter_blacklist = self.get_config('reporter_blacklist', default=[])
        reporter_blacklist = ','.join(reporter_blacklist)

        return {
            # Ignore closed bugs.
            'bug_status': '__open__',

            # Check only recently opened bugs.
            'f1': 'creation_ts', 'o1': 'greaterthan', 'v1': start_date,

            'f2': 'reporter', 'o2': 'nowords', 'v2': reporter_blacklist,
        }

    def get_bugs(self, date='today', bug_ids=[]):
        # Retrieve bugs to analyze.
        bugs, probs = super().get_bugs(date=date, bug_ids=bug_ids)
        if len(bugs) == 0:
            return {}

        # Get the encoded type.
        indexes = probs.argmax(axis=-1)
        # Apply inverse transformation to get the type name from the encoded value.
        suggestions = self.model.clf._le.inverse_transform(indexes)

        results = {}
        for bug, prob, index, suggestion in zip(bugs, probs, indexes, suggestions):
            assert suggestion in {'defect', 'enhancement', 'task'}, f'Suggestion {suggestion} is invalid'  # noqa

            if prob[index] < self.get_config('confidence_threshold'):
                continue

            if bug['type'] == suggestion:
                continue

            results[bug['id']] = {
                'id': bug['id'],
                'summary': self.get_summary(bug),
                'type': bug['type'],
                'bugbug_type': suggestion,
                'confidence': int(round(100 * prob[index])),
            }

        return results


if __name__ == '__main__':
    DefectEnhancementTask().run()