from abc import abstractmethod
import time
from wtforms import ValidationError
from loguru import logger
from flask_babel import gettext

class Importer():
    remaining_data = []
    new_uuids = []
    good = 0

    def __init__(self):
        self.new_uuids = []
        self.good = 0
        self.remaining_data = []
        self.import_profile = None
        self.limit_reported = False

    @abstractmethod
    def run(self,
            data,
            flash,
            datastore):
        pass

    def watch_limit_hit(self, datastore, flash):
        """True once PAGE_WATCH_LIMIT leaves no room - the caller must then stop importing.

        Asked before each add_watch() so the limit is reported once for the whole file.
        add_watch() would otherwise flash the same error again for every remaining row.
        """
        if not datastore.watch_limit_reached():
            return False

        if not self.limit_reported:
            self.limit_reported = True
            flash(datastore.watch_limit_message(), 'error')

        return True


