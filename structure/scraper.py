import re
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional

import requests

from dashboard.models import Student, User

endpoint = 'https://my.loreto.ac.uk/'


class LandingPageParser:
    """Class for parsing the Loreto landing page."""

    def _set_regex_group(self, page: bytes, name: str, pattern: bytes):
        """Set the Student data to the first group of the given match."""
        match = re.search(pattern, page)
        if match is not None:
            setattr(self.student, name, match.group(1).decode())

    def _get_short_timetable(self):
        """Get the timetable for the current day."""
        timetable = []
        pattern = re.compile(
            b'TimetableEntry .*?>(?P<time>[0-9 -:]+)'
            b'.*?(?P<room>[()A-Z0-9]+)'
            b'.*?(?P<teacher>[()A-Za-z0-9 -]+) ',
            re.DOTALL
        )
        for time, room, teacher in pattern.findall(self.page):
            room = room.strip(b'()')
            subject, teacher = teacher.split(b' - ')
            timetable.append(
                {
                    'time': time.decode(),
                    'room': room.decode(),
                    'subject': subject.decode(),
                    'teacher': teacher.decode()
                }
            )
        self.student.short_timetable = timetable

    def _get_timetable(self):
        """Get the timetable for the current week."""
        timetable = {
            'Monday': [],
            'Tuesday': [],
            'Wednesday': [],
            'Thursday': [],
            'Friday': []
        }
        day_meta = '<h3>{0}</h3>(.*?)</div>'
        lesson_meta = (
            '<strong>(?P<time>[0-9: -]*):</strong>'
            ' (?P<subject>[A-Za-z ]*) in (?P<room>[A-Z0-9]*)'
            ' with (?P<teacher>[A-Za-z ]*)'
        )
        now = datetime.now()
        start = now - timedelta(days=now.weekday() - 7)
        match: Optional[re.Match] = None
        while match is None:
            start = start - timedelta(days=7)
            beginning = start.strftime('%Y-%m-%d')
            response: bytes = requests.post(
                f'{endpoint}attendance/timetable/studentWeek',
                data={'week': beginning, 'student_user_id': self.user_id},
                auth=(self.user.username, self.user.password),
                headers={'X-Requested-With': 'XMLHttpRequest'}
            ).content
            match = re.search(
                day_meta.format('Monday').encode(), response, re.DOTALL
            )
        for day, lessons in timetable.items():
            match = re.search(
                day_meta.format(day).encode(), response, re.DOTALL
            )
            content = match.group(1).decode()
            for match in re.finditer(lesson_meta, content, re.DOTALL):
                lesson = match.groupdict()
                start, _, end = lesson.pop('time').strip().partition(' - ')
                lesson['start'] = start
                lesson['end'] = end
                lessons.append(lesson)
        self.student.timetable = timetable

    def __init__(self, user: User, path: Optional[str] = None):
        """Add all thread objects without starting them."""
        if path is None:
            self.page = requests.get(
                endpoint, auth=(user.username, user.password)
            ).content
        else:
            self.page = open(path, 'rb').read()
        self.user = user
        self.threads: set = set()
        self.student: Student = Student()
        user_id = re.search(
            br'UserId = "(\d+)"', self.page
        )
        if user_id is not None:
            self.user_id: int = int(user_id.group(1))
        patterns = {
            'name': b'fullName: "([A-Za-z ]+)"',
            'username': b'username: "([A-Za-z0-9]+)"',
            'avatar': b'base64,(.*?)">',
            'reference_number': br'Reference: </dt>\s+<dd>([A-Z0-9]+)',
            'tutor': b'Tutor: </dt> <dd> (.*?) </dd>'
        }
        self.threads.add(Thread(target=self._get_short_timetable))
        self.threads.add(Thread(target=self._get_timetable))
        for key, pattern in patterns.items():
            self.threads.add(
                Thread(
                    target=self._set_regex_group,
                    args=(self.page, key, pattern)
                )
            )

    def parse(self) -> Student:
        """Parse the webpage content and return the resulting Student."""
        for thread in self.threads:
            thread.start()
        print('Capture threads started...')
        for thread in self.threads:
            thread.join()
        print('Capture threads complete!')
        self.student.email = '{0}@student.loreto.ac.uk'.format(
            self.student.username
        )
        return self.student


def valid_user(user: User) -> bool:
    """Take a User object and validate credentials."""
    print('Validating user...')
    return requests.get(
        endpoint, auth=(user.username, user.password)
    ).status_code == 200


def create_student(user: User) -> Student:
    """Take a User object and intialize a Student object."""
    parser = LandingPageParser(user)
    student = parser.parse()
    print('Created student:', repr(student.name))
    return student
