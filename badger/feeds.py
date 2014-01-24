"""Feeds for badge"""
import logging
import datetime
import hashlib
import urllib

from django.contrib.syndication.views import Feed, FeedDoesNotExist
from django.utils.feedgenerator import (SyndicationFeed, Rss201rev2Feed,
                                        Atom1Feed, get_tag_uri)
import django.utils.simplejson as json
from django.shortcuts import get_object_or_404

from django.contrib.auth.models import User
from django.conf import settings

try:
    from tower import ugettext_lazy as _
except ImportError:
    from django.utils.translation import ugettext_lazy as _

try:
    from commons.urlresolvers import reverse
except ImportError:
    from django.core.urlresolvers import reverse

from . import validate_jsonp
from .models import (Badge, Award, Nomination, Progress,
                     BadgeAwardNotAllowedException,
                     DEFAULT_BADGE_IMAGE)


MAX_FEED_ITEMS = getattr(settings, 'BADGER_MAX_FEED_ITEMS', 50)


class OBIJSONFeedGenerator(SyndicationFeed):
    """OBI JSON feed generator"""

    serialization_method = 'as_obi_assertion'
    mime_type = 'application/json'

    def _encode_complex(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()

    def build_item(self, item):
        request = self.feed['request']
        return getattr(item['obj'], self.serialization_method)(request)

    def build_feed(self):
        return dict(badges=[self.build_item(item) for item in self.items])

    def write(self, outfile, encoding):
        request = self.feed['request']

        # Check for a callback param, validate it before use
        callback = request.GET.get('callback', None)
        if callback is not None:
            if not validate_jsonp.is_valid_jsonp_callback_value(callback):
                callback = None

        # Build the JSON string, wrapping it in a callback param if necessary.
        json_string = json.dumps(self.build_feed(),
                                 default=self._encode_complex)
        if callback:
            outfile.write('%s(%s)' % (callback, json_string))
        else:
            outfile.write(json_string)


class BaseFeed(Feed):
    """Base feed for all of badger, allows switchable generator from URL route
    and other niceties"""
    # TODO:liberate - Can this class be a generally-useful lib?

    json_feed_generator = OBIJSONFeedGenerator
    rss_feed_generator = Rss201rev2Feed
    atom_feed_generator = Atom1Feed

    def __call__(self, request, *args, **kwargs):
        self.request = request
        return super(BaseFeed, self).__call__(request, *args, **kwargs)

    def get_object(self, request, format):
        self.link = request.build_absolute_uri('/')
        if format == 'json':
            self.feed_type = self.json_feed_generator
        elif format == 'rss':
            self.feed_type = self.rss_feed_generator
        else:
            self.feed_type = self.atom_feed_generator
        return super(BaseFeed, self).get_object(request)

    def feed_extra_kwargs(self, obj):
        return {'request': self.request, 'obj': obj, }

    def item_extra_kwargs(self, obj):
        return {'obj': obj, }

    def item_pubdate(self, obj):
        return obj.created

    def item_author_link(self, obj):
        if not obj.creator or not hasattr(obj.creator, 'get_absolute_url'):
            return None
        else:
            return self.request.build_absolute_uri(
                obj.creator.get_absolute_url())

    def item_author_name(self, obj):
        if not obj.creator:
            return None
        else:
            return '%s' % obj.creator

    def item_description(self, obj):
        if obj.image:
            image_url = obj.image.url
        else:
            image_url = '%simg/default-badge.png' % settings.MEDIA_URL
        return """
            <div>
                <a href="%(href)s"><img alt="%(alt)s" src="%(image_url)s" /></a>
            </div>
        """ % dict(
            alt=unicode(obj),
            href=self.request.build_absolute_uri(obj.get_absolute_url()),
            image_url=self.request.build_absolute_uri(image_url)
        )


class AwardActivityStreamJSONFeedGenerator(OBIJSONFeedGenerator):
    serialization_method = 'as_obi_assertion'


class AwardActivityStreamAtomFeedGenerator(Atom1Feed):
    pass


class AwardsFeed(BaseFeed):
    """Base class for all feeds listing awards"""
    title = _(u'Recently awarded badges')
    subtitle = None

    json_feed_generator = AwardActivityStreamJSONFeedGenerator
    atom_feed_generator = AwardActivityStreamAtomFeedGenerator

    def item_title(self, obj):
        return _(u'{badgetitle} awarded to {username}').format(
            badgetitle=obj.badge.title, username=obj.user.username)

    def item_author_link(self, obj):
        if not obj.creator:
            return None
        else:
            return self.request.build_absolute_uri(
                reverse('badger.views.awards_by_user',
                        args=(obj.creator.username,)))

    def item_link(self, obj):
        return self.request.build_absolute_uri(
            reverse('badger.views.award_detail',
                    args=(obj.badge.slug, obj.pk, )))


class AwardsRecentFeed(AwardsFeed):
    """Feed of all recent badge awards"""

    def items(self):
        return (Award.objects
                .order_by('-created')
                .all()[:MAX_FEED_ITEMS])


class AwardsByUserFeed(AwardsFeed):
    """Feed of recent badge awards for a user"""

    def get_object(self, request, format, username):
        super(AwardsByUserFeed, self).get_object(request, format)
        user = get_object_or_404(User, username=username)
        self.title = _(u'Badges recently awarded to {username}').format(
            username=user.username)
        self.link = request.build_absolute_uri(
            reverse('badger.views.awards_by_user', args=(user.username,)))
        return user

    def items(self, user):
        return (Award.objects
                .filter(user=user)
                .order_by('-created')
                .all()[:MAX_FEED_ITEMS])


class AwardsByBadgeFeed(AwardsFeed):
    """Feed of recent badge awards for a badge"""

    def get_object(self, request, format, slug):
        super(AwardsByBadgeFeed, self).get_object(request, format)
        badge = get_object_or_404(Badge, slug=slug)
        self.title = _(u'Recent awards of "{badgetitle}"').format(
            badgetitle=badge.title)
        self.link = request.build_absolute_uri(
            reverse('badger.views.awards_by_badge', args=(badge.slug,)))
        return badge

    def items(self, badge):
        return (Award.objects
                .filter(badge=badge).order_by('-created')
                .all()[:MAX_FEED_ITEMS])


class BadgesJSONFeedGenerator(OBIJSONFeedGenerator):
    serialization_method = 'as_obi_serialization'


class BadgesFeed(BaseFeed):
    """Base class for all feeds listing badges"""
    title = _(u'Recently created badges')

    json_feed_generator = BadgesJSONFeedGenerator

    def item_title(self, obj):
        return obj.title

    def item_link(self, obj):
        return self.request.build_absolute_uri(
            reverse('badger.views.detail',
                    args=(obj.slug, )))


class BadgesRecentFeed(BadgesFeed):

    def items(self):
        return (Badge.objects
                .order_by('-created')
                .all()[:MAX_FEED_ITEMS])


class BadgesByUserFeed(BadgesFeed):
    """Feed of badges recently created by a user"""

    def get_object(self, request, format, username):
        super(BadgesByUserFeed, self).get_object(request, format)
        user = get_object_or_404(User, username=username)
        self.title = _(u'Badges recently created by {username}').format(
            username=user.username)
        self.link = request.build_absolute_uri(
            reverse('badger.views.badges_by_user', args=(user.username,)))
        return user

    def items(self, user):
        return (Badge.objects
                .filter(creator=user)
                .order_by('-created')
                .all()[:MAX_FEED_ITEMS])
