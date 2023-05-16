from collections import OrderedDict
from html.parser import HTMLParser

class WKContextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_context = 0
        self.await_pattern = None
        self.await_collo = None
        self.await_collo_text = None
        self.cur_ja = None
        self.cur_en = None

        self.patterns = OrderedDict()
        self.collos = dict()

    def attr_contains(self, attrs, attr, needle):
        for a in attrs:
            if a[0] == attr and (f"{needle} " in a[1] or a[1].endswith(needle)):
                return True
        return False

    def get_attr(self, attrs, attr):
        for a in attrs:
            if a[0] == attr:
                return a[1]
        return None

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            if self.in_context or self.attr_contains(attrs, "class", "subject-section--context"):
                self.in_context += 1
                return
        if not self.in_context:
            return

        if self.attr_contains(attrs, "class", "subject-collocations__pattern-name"):
            self.await_pattern = self.get_attr(attrs, "aria-controls")
        elif self.attr_contains(attrs, "class", "subject-collocations__pattern-collocation"):
            self.await_collo = self.get_attr(attrs, "id")
        elif self.await_collo and self.attr_contains(attrs, "class", "wk-text"):
            self.await_collo_text = self.get_attr(attrs, "lang") or "en"

    def handle_endtag(self, tag):
        if self.in_context and tag == "section":
            self.in_context -= 1

    def handle_data(self, data):
        if self.await_pattern:
            self.patterns[self.await_pattern] = data
            self.collos[self.await_pattern] = []
            self.await_pattern = None
        elif self.await_collo and self.await_collo_text:
            if self.await_collo_text == "en":
                self.cur_en = data
            else:
                self.cur_ja = data
            if self.cur_en and self.cur_ja:
                self.collos[self.await_collo].append((self.cur_ja, self.cur_en))
                self.cur_ja = None
                self.cur_en = None
            self.await_collo_text = None
