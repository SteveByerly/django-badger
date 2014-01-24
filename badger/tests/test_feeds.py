import logging
import feedparser
import json

from django.conf import settings

from django.http import HttpRequest
from django.test.client import Client

from pyquery import PyQuery as pq

from nose.tools import assert_equal, with_setup, assert_false, eq_, ok_
from nose.plugins.attrib import attr

from django.template.defaultfilters import slugify

from django.contrib.auth.models import User

try:
    from commons.urlresolvers import reverse
except ImportError:
    from django.core.urlresolvers import reverse

from . import BadgerTestCase

from badger.models import (Badge, Award, Progress,
        BadgeAwardNotAllowedException)
from badger.utils import get_badge, award_badge


class BadgerFeedsTest(BadgerTestCase):

    def setUp(self):
        self.testuser = self._get_user()
        self.client = Client()
        Award.objects.all().delete()

    def tearDown(self):
        Award.objects.all().delete()
        Badge.objects.all().delete()

    def test_award_atom_feeds(self):
        """Can view award atom feeds"""
        user = self._get_user()
        user2 = self._get_user(username='tester2')

        b1, created = Badge.objects.get_or_create(creator=user,
                                                  title="Code Badge #1")
        award = b1.award_to(user2)

        # The award should show up in each of these feeds.
        feed_urls = (
            reverse('badger.feeds.awards_recent', 
                    args=('atom', )),
            reverse('badger.feeds.awards_by_badge', 
                    args=('atom', b1.slug, )),
            reverse('badger.feeds.awards_by_user',
                    args=('atom', user2.username,)),
        )

        # Check each of the feeds
        for feed_url in feed_urls:
            r = self.client.get(feed_url, follow=True)

            # The feed should be parsed without issues by feedparser
            feed = feedparser.parse(r.content)
            eq_(0, feed.bozo)

            # Look through entries for the badge title
            found_it = False
            for entry in feed.entries:
                if b1.title in entry.title and user2.username in entry.title:
                    found_it = True

            ok_(found_it)

    def test_badge_json_feeds(self):
        user = self._get_user()
        user2 = self._get_user(username='tester2')

        b1, created = Badge.objects.get_or_create(creator=user,
                                                  title="Code Badge #1")

        # The award should show up in each of these feeds.
        feed_urls = (
            reverse('badger.feeds.badges_recent', 
                    args=('json', )),
        )

        # Check each of the feeds
        for feed_url in feed_urls:
            r = self.client.get(feed_url, follow=True)

            # The feed should be parsed without issues by feedparser
            feed = json.loads(r.content)

            ok_('badges' in feed)
            b1_url = ('http://testserver%s' %
                      b1.get_absolute_url())
            found_it = False
            for badge in feed['badges']:
                if badge['criteria'] == b1_url:
                    found_it = True
            
            ok_(found_it)

    def test_award_json_feeds(self):
        user = self._get_user()
        user2 = self._get_user(username='tester2')

        b1, created = Badge.objects.get_or_create(creator=user,
                                                  title="Code Badge #1")
        award = b1.award_to(user2)

        # The award should show up in each of these feeds.
        feed_urls = (
            reverse('badger.feeds.awards_recent', 
                    args=('json', )),
            reverse('badger.feeds.awards_by_badge', 
                    args=('json', b1.slug, )),
            reverse('badger.feeds.awards_by_user',
                    args=('json', user2.username,)),
        )

        # Check each of the feeds
        for feed_url in feed_urls:
            r = self.client.get(feed_url, follow=True)

            # The feed should be parsed without issues by feedparser
            feed = json.loads(r.content)

            ok_('badges' in feed)
            b1_url = ('http://testserver%s' %
                      b1.get_absolute_url(format='json'))
            found_it = False
            for badge in feed['badges']:
                if badge['badge'] == b1_url:
                    found_it = True
            
            ok_(found_it)

    def _get_user(self, username="tester", email="tester@example.com",
            password="trustno1"):
        (user, created) = User.objects.get_or_create(username=username,
                defaults=dict(email=email))
        if created:
            user.set_password(password)
            user.save()
        return user
