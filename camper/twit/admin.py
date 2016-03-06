from django.contrib import admin

from camper.twit.models import SessionBlockTweet


class SessionBlockTweetAdmin(admin.ModelAdmin):
    list_display = ('__unicode__', 'text', 'sent_at')


admin.site.register(SessionBlockTweet, SessionBlockTweetAdmin)
