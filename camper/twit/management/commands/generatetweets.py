import datetime

from dateutil.parser import parse as dateparse
from django.core.management.base import BaseCommand, make_option
from django.conf import settings
from django.utils import timezone

from camper.sked.models import Session, Event
from camper.twit.models import SessionBlockTweet, AlreadyAssignedError, TweetTooLongError


class Command(BaseCommand):
    help = '''Generates Session tweets for a given timeslot.'''

    option_list = BaseCommand.option_list + (
        make_option('--event-id',
                    action='store',
                    dest='event_id',
                    default=Event.objects.current().id,
                    help='''The ID of the event to tweet sessions for
                            '''),
        make_option('--timeslot',
                    action='store',
                    dest='timeslot',
                    default='next',
                    help='''The ISO datetime that the events being tweeted
                            should start at'''),
        make_option('--skip-if-delta',
                    action='store',
                    dest='skipdelta',
                    default='600',
                    help='''A timedelta in seconds that the timeslot should fall
                            within in order to trigger tweet generation'''),
    )

    def handle(self, *args, **options):
        event = Event.objects.get(pk=int(options.get('event_id')))
        qs = Session.objects.none()
        timeslot = options.get('timeslot')
        skipdelta = options.get('skipdelta')

        if skipdelta:
            skipdelta = datetime.timedelta(seconds=int(options.get('skipdelta')))
        else:
            skipdelta = None

        if timeslot == 'next':
            qs = Session.objects.next().filter(event=event)
            timeslot = qs[0].start_time
        else:
            timeslot = dateparse(timeslot).replace(tzinfo=timezone.get_current_timezone())
            qs = Session.objects.filter(event=event, start_time=timeslot, is_public=True)

        if skipdelta is not None and timezone.now() + skipdelta < timeslot:
            print('Sessions are too far in the future, aborting.')
            return

        tweets = SessionBlockTweet.objects.filter(event=event, timeslot=timeslot).count()
        if tweets:
            print('Tweets have already been generated for this timeslot. Run ./manage.py destroytweets --event-id=%s --timeslot=%s and try again' % (event.id, timeslot.isoformat()))
        tweet = SessionBlockTweet.objects.create(event=event, timeslot=timeslot)

        for session in qs:
            try:
                tweet.add_session(session)
            except AlreadyAssignedError:
                continue
            except TweetTooLongError:
                SessionBlockTweet.objects.create(event=event, timeslot=timeslot, previous=tweet)
                tweet.save()
                tweet = tweet.next
                try:
                    tweet.add_session(session)
                except TweetTooLongError:
                    continue
            tweet.save()
