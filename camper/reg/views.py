import datetime
import json
import braintree
import slack

from collections import defaultdict

from django.shortcuts import render_to_response
from django.template.loader import render_to_string
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.forms.util import ErrorList
from django.http import Http404, HttpResponse
from django.contrib.auth.decorators import user_passes_test

from camper.reg.models import *
from camper.reg.forms import *
from camper.reg.email_utils import *
from camper.reg.reports import *
from camper.reg.badges import require_staff_code
from camper.sked.utils import get_current_event


def register(request):
    if get_current_event().registration_is_open:
        return _open_register(request)
    else:
        return _closed_register(request)


@require_staff_code
def register_override(request):
    return _open_register(request)


def _closed_register(request):
    payment_form = PaymentForm()
    ticket_form = TicketForm()

    ticket_types = TicketType.objects.filter(event=get_current_event(), enabled=True, onsite=True).order_by('position')

    return render_to_response('reg/register.html', {'ticket_form': ticket_form, 'payment_form': payment_form, 'ticket_types': ticket_types, 'BRAINTREE_CSE_KEY': getattr(settings, "BRAINTREE_CSE_KEY", ""), 'event': get_current_event(), 'registration_is_open': False}, context_instance=RequestContext(request))


def _open_register(request):
    payment_form = PaymentForm()
    ticket_form = TicketForm()

    ticket_types = TicketType.objects.filter(event=get_current_event(), enabled=True, online=True).order_by('position')

    return render_to_response('reg/register.html', {'ticket_form': ticket_form, 'payment_form': payment_form, 'ticket_types': ticket_types, 'BRAINTREE_CSE_KEY': getattr(settings, "BRAINTREE_CSE_KEY", ""), 'event': get_current_event(), 'registration_is_open': True}, context_instance=RequestContext(request))


@never_cache
def whos_going(request):
    attendees = Ticket.objects.filter(event=get_current_event(), success=True).order_by('-id')
    out = [{
        'first_name': a.first_name,
        'last_name': a.last_name,
        'organization': a.organization,
        'twitter': a.clean_twitter
    } for a in attendees]
    return HttpResponse(json.dumps({'attendees':out}), content_type="application/json")


@csrf_exempt
def save(request):
    if request.method != "POST":
        raise Http404
    try:
        data = json.loads(request.raw_post_data)
    except:
        raise Http404

    sale = Sale()
    out = {'ticket_forms': [], 'success': True}
    types = defaultdict(int)
    valid_tickets = []
    for form_id, form_data in data['ticket_forms'].items():
        form_response = {'id': form_id}
        form = TicketForm(form_data)
        if form.is_valid():
            form_response['success'] = True
            valid_tickets.append(form)
            types[int(form_data['type'])] += 1
        else:
            out['success'] = False
            form_response['success'] = False
            form_response['text'] = render_to_string('reg/partials/ticket_form.html', {'ticket_form': form}, context_instance=RequestContext(request))
        out['ticket_forms'].append(form_response)

    if out['success']:
        # get all the models ready
        sale.event = get_current_event()
        sale.amount = 0
        sale.save()

        tickets = []
        for ticket_form in valid_tickets:
            ticket = ticket_form.save(commit=False)
            ticket.event = get_current_event()
            ticket.sale = sale
            ticket.save()

            tickets.append(ticket)

            if getattr(settings, 'SLACK_ENABLED', False):
                try:
                    slack.post_registration(ticket)
                except:
                    pass

        # tickets are good, so confirm price
        price = get_price_data(tickets=types, coupon=data.get('coupon', None))

        # save the coupon code if there is one
        if 'coupon' in price:
            sale.coupon_code = CouponCode.objects.get(event=get_current_event(), code=price['coupon'])

        if price['price'] > 0:
            # there should have been a payment form
            form_response = {'success': True}
            payment_form = PaymentForm(data.get('payment_form', {}))
            if payment_form.is_valid():
                # do the prices match?
                if price['price'] != float(data['expected_price']):
                    # something is wrong
                    payment_form._errors["__all__"] = ErrorList([u"There was a problem calculating your payment due. Please contact us for further assistance."])
                    form_response['success'] = False
                else:
                    # moving onward -- update all the sale forms with the relevant fields
                    sale.first_name = payment_form['first_name'].value()
                    sale.last_name = payment_form['last_name'].value()
                    sale.email = payment_form['email'].value()

                    sale.address1 = payment_form['address1'].value()
                    sale.address2 = payment_form['address2'].value()
                    sale.city = payment_form['city'].value()
                    sale.state = payment_form['state'].value()
                    sale.zip = payment_form['zip'].value()

                    sale.amount = price['price']
                    sale.payment_type = 'online_credit'

                    sale.save()

                    # now pay for things
                    result = braintree.Transaction.sale({
                        "amount": "%.2f" % price['price'],
                        "credit_card": {
                            "number": payment_form["number"].value(),
                            "cvv": payment_form["cvv"].value(),
                            "expiration_month": payment_form["exp_month"].value(),
                            "expiration_year": payment_form["exp_year"].value()
                        },
                        "options": {
                            "submit_for_settlement": True
                        }
                    })

                    if result.is_success:
                        # everything is wonderful!
                        # save everything
                        sale.success = True
                        sale.transaction_id = result.transaction.id
                        sale.save()

                        for ticket in tickets:
                            ticket.success = True
                            ticket.save()

                        # Create BOGO coupon for the user, if promotion is ongoing
                        if ('coupon' not in price and
                                datetime.datetime.now() >= datetime.datetime.strptime(settings.BOGO_START_DATE, '%Y-%m-%d') and
                                datetime.datetime.now() <= datetime.datetime.strptime(settings.BOGO_END_DATE, '%Y-%m-%d')):
                            bogo_code = CouponCode(
                                code='BOGO-{}-{}'.format(sale.email, sale.id),
                                discount=100,
                                max_tickets=1,
                                is_staff=False
                            )
                            bogo_code.save()

                    else:
                        if hasattr(result.transaction, "id"):
                            sale.transaction_id = result.transaction.id
                            sale.save()
                        payment_form._errors["__all__"] = ErrorList([u"There was a problem processing your payment: %s" % result.message])
                        form_response['success'] = False
            else:
                form_response['success'] = False

            if not form_response['success']:
                out['success'] = False
                form_response['text'] = render_to_string('reg/partials/payment_form.html', {'payment_form': payment_form}, context_instance=RequestContext(request))

                # avoid having junk hanging around in the DB
                sale.delete()
            out['payment_form'] = form_response
        else:
            # we can blindly accept all the tickets, since no payment is necessary
            sale.payment_type = 'none'
            sale.success = True
            sale.save()

            for ticket in tickets:
                ticket.success = True
                ticket.save()
    else:
        # if they submitted a payment form, validate it anyway so we can offer useful feedback
        if 'payment_form' in data:
            payment_form = PaymentForm(data['payment_form'])
            if payment_form.is_valid():
                form_response = {'success': True}
            else:
                form_response = {'success': False, 'text': render_to_string('reg/partials/payment_form.html', {'payment_form': payment_form}, context_instance=RequestContext(request))}
            out['payment_form'] = form_response

    if out['success']:
        send_sale_email(sale.id)

    return HttpResponse(json.dumps(out), content_type="application/json")


@csrf_exempt
def price_check(request):
    if request.method != "POST":
        raise Http404
    try:
        data = json.loads(request.raw_post_data)
    except:
        raise Http404

    return HttpResponse(json.dumps(get_price_data(tickets=data['tickets'], coupon=data.get('coupon', None))), content_type="application/json")


# utilities
def get_price_data(tickets={}, coupon=None):
    out = {}
    total = 0
    total_qty = 0
    for tk, qty in tickets.items():
        ticket = TicketType.objects.get(id=tk)
        total += float(ticket.price) * qty
        total_qty += qty

    if coupon:
        cpl = list(CouponCode.objects.filter(event=get_current_event(), code=coupon))
        if len(cpl):
            cp = cpl[0]
            too_many = False
            if cp.max_tickets != 0:
                so_far = Ticket.objects.filter(success=True, sale__coupon_code=cp).count()
                left = cp.max_tickets - so_far
                if total_qty > left:
                    too_many = True

            if too_many:
                out['coupon_error'] = "Not enough tickets are left for this coupon to cover your order."
            else:
                out['coupon'] = coupon
                total -= (cp.discount / 100.0) * total
        else:
            out['coupon_error'] = "Coupon code not found."
    out['price'] = total

    return out


# payment
braintree.Configuration.configure(
    braintree.Environment.Production if getattr(settings, "BRAINTREE_ENVIRONMENT", "sandbox") == "production" else braintree.Environment.Sandbox,
    merchant_id=getattr(settings, "BRAINTREE_MERCHANT_ID", ""),
    public_key=getattr(settings, "BRAINTREE_PUBLIC_KEY", ""),
    private_key=getattr(settings, "BRAINTREE_PRIVATE_KEY", "")
)


# info pages
@never_cache
@user_passes_test(lambda user: user.is_staff, login_url="/staff/login")
def stats(request):
    stats = get_registration_report()
    return render_to_response('reg/stats.html', stats, context_instance=RequestContext(request))


@never_cache
@user_passes_test(lambda user: user.is_staff, login_url="/staff/login")
def volunteer_export(request):
    return HttpResponse(get_volunteer_export(), content_type="text/csv")


@never_cache
@user_passes_test(lambda user: user.is_staff, login_url="/staff/login")
def attendee_export(request):
    return HttpResponse(get_attendee_export(), content_type="text/csv")
