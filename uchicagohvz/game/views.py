from django.shortcuts import *
from django.conf import settings
from django.db import transaction
from django.contrib import messages
from django.http import *
from django.core.exceptions import *
from django.views.generic import *
from django.views.generic.edit import BaseFormView
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import *
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from rest_framework.response import Response
from uchicagohvz.game.models import *
from uchicagohvz.game.forms import *
from uchicagohvz.game.data_apis import *
from uchicagohvz.game.serializers import *
from uchicagohvz.game.tasks import *
from uchicagohvz.users.models import *

# Create your views here.

class ListGames(ListView):
	model = Game
	template_name = 'game/list.html'

class ShowGame(DetailView):
	model = Game
	template_name = 'game/show.html'

	def get_context_data(self, **kwargs):
		context = super(ShowGame, self).get_context_data(**kwargs)
		if self.object.status in ('in_progress', 'finished'):
			if self.object.get_active_players().count() > 0:
				context['humans_percent'] = int(round(100 * float(self.object.get_humans().count()) / self.object.get_active_players().count(), 0))
				context['zombies_percent'] = int(round(100 * float(self.object.get_zombies().count()) / self.object.get_active_players().count(), 0))
				if self.object.status == "in_progress":
					context['sms_code_number'] = settings.NEXMO_NUMBER
				context['kills_per_hour'] = kills_per_hour(self.object)
				context['survival_by_dorm'] = survival_by_dorm(self.object)
				context['most_courageous_dorms'] = most_courageous_dorms(self.object)
				context['most_infectious_dorms'] = most_infectious_dorms(self.object)
				context['top_humans'] = top_humans(self.object)[:10]
				context['top_zombies'] = top_zombies(self.object)[:10]
		if self.request.user.is_authenticated():
			in_game = Player.objects.filter(game=self.object, user=self.request.user).exists()
			if in_game:
				player = Player.objects.get(game=self.object, user=self.request.user)
				context['player'] = player
				if self.object.status in ('in_progress', 'finished') and player.active:
					if player.human:
						context['player_rank'] = player.human_rank
					else:
						context['player_rank'] = player.zombie_rank
		return context

class RegisterForGame(FormView):
	form_class = GameRegistrationForm
	template_name = "game/register.html"

	@method_decorator(login_required)
	def dispatch(self, request, *args, **kwargs):
		self.game = get_object_or_404(Game, id=self.kwargs['pk'])
		if self.game.status != 'registration':
			return HttpResponseForbidden()
		if Player.objects.filter(game=self.game, user=request.user).exists():
			return HttpResponseRedirect(self.game.get_absolute_url())
		return super(RegisterForGame, self).dispatch(request, *args, **kwargs)

	def form_valid(self, form):
		player = form.save(commit=False)
		player.user = self.request.user
		player.game = self.game
		player.save()
		messages.success(self.request, "You are now registered for %s!" % (self.game.name))
		return HttpResponseRedirect(self.game.get_absolute_url())

	def get_context_data(self, **kwargs):
		context = super(RegisterForGame, self).get_context_data(**kwargs)
		context['game'] = self.game
		return context

class EnterBiteCode(FormView):
	form_class = BiteCodeForm
	template_name = 'game/enter-bite-code.html'

	@method_decorator(login_required)
	def dispatch(self, request, *args, **kwargs):
		return super(EnterBiteCode, self).dispatch(request, *args, **kwargs)

	def form_valid(self, form):
		victim = form.victim
		kill = victim.kill_me(self.killer)
		if kill:
			send_death_notification.delay(kill)
			kill.lat = form.cleaned_data.get('lat')
			kill.lng = form.cleaned_data.get('lng')
			kill.save()
			messages.success(self.request, "Bite code entered successfully! %s has joined the ranks of the undead." % (victim.user.get_full_name()))
		return HttpResponseRedirect(self.game.get_absolute_url())

	def get_form_kwargs(self):
		kwargs = super(EnterBiteCode, self).get_form_kwargs()
		self.game = get_object_or_404(Game, id=self.kwargs['pk'])
		if self.game.status == 'in_progress':
			self.killer = get_object_or_404(Player, game=self.game, active=True, human=False, user=self.request.user)
			kwargs['killer'] = self.killer
			kwargs['require_location'] = True
			return kwargs
		else:
			raise PermissionDenied

	def get_context_data(self, **kwargs):
		context = super(EnterBiteCode, self).get_context_data(**kwargs)
		return context

class AddKillGeotag(UpdateView):
	form_class = AddKillGeotagForm
	model = Kill
	template_name = 'game/add-kill-geotag.html'

	@method_decorator(login_required)
	def dispatch(self, request, *args, **kwargs):
		return super(AddKillGeotag, self).dispatch(request, *args, **kwargs)

	def get_object(self, queryset=None):
		kill = super(AddKillGeotag, self).get_object()
		if kill.killer.user == self.request.user and not (kill.lat and kill.lng):
			return kill
		raise PermissionDenied

	def form_valid(self, form):
		kill = self.object
		kill.lat = form.cleaned_data.get('lat')
		kill.lng = form.cleaned_data.get('lng')
		kill.save()
		messages.success(self.request, 'Kill geotagged successfully.')
		return HttpResponseRedirect(kill.killer.game.get_absolute_url())

class SubmitCodeSMS(APIView):
	@method_decorator(csrf_exempt)
	def post(self, request, *args, **kwargs):
		data = {k: v for (k, v) in request.DATA.iteritems()}
		data['message_timestamp'] = data.pop('message-timestamp', '') # workaround for hyphen in field name
		data['network_code'] = data.pop('network-code', '')
		serializer = NexmoSMSSerializer(data=data)
		code = data.get('text', '').lower().strip()
		if serializer.is_valid():
			data = serializer.object
			phone_number = "%s-%s-%s" % (data['msisdn'][1:4], data['msisdn'][4:7], data['msisdn'][7:11])
			try:
				profile = Profile.objects.get(phone_number=phone_number)
			except:
				return Response()
			games = Game.objects.all().order_by('-start_date')
			for game in games:
				if game.status == 'in_progress':
					try:
						player = Player.objects.get(game=game, user=profile.user)
					except Player.DoesNotExist:
						return Response()
					form = BiteCodeForm(data={'bite_code': code}, killer=player)
					# player is the killer
					if form.is_valid():
						kill = form.victim.kill_me(player)
						if kill:
							send_sms_confirmation.delay(player, kill)
							send_death_notification.delay(kill)
						return Response()
					form = AwardCodeForm(data={'code': code}, player=player)
					if form.is_valid():
						with transaction.atomic():
							award = form.award
							award.players.add(player)
							award.save()
						send_sms_confirmation.delay(player, award)
						return Response()
		# player has a valid number but entered an invalid code
		if code:
			send_sms_invalid_code.delay(profile, code)
		return Response()

class SubmitAwardCode(BaseFormView):
	form_class = AwardCodeForm
	http_method_names = ['post']

	@method_decorator(login_required)
	def dispatch(self, request, *args, **kwargs):
		return super(SubmitAwardCode, self).dispatch(request, *args, **kwargs)

	@transaction.atomic
	def form_valid(self, form):
		award = form.award
		award.players.add(self.player)
		award.save()
		messages.success(self.request, "Code entry accepted!")
		return HttpResponseRedirect(self.game.get_absolute_url())

	def form_invalid(self, form):
		for e in form.non_field_errors():
			messages.error(self.request, e)
		return HttpResponseRedirect(self.game.get_absolute_url())

	def get_form_kwargs(self):
		kwargs = super(SubmitAwardCode, self).get_form_kwargs()
		self.game = get_object_or_404(Game, id=self.kwargs['pk'])
		if self.game.status == 'in_progress':
			self.player = get_object_or_404(Player, game=self.game, active=True, user=self.request.user)
			kwargs['player'] = self.player
			return kwargs
		else:
			raise PermissionDenied

class ShowPlayer(DetailView):
	model = Player
	template_name = 'game/show_player.html'

	def get_object(self, queryset=None):
		return get_object_or_404(Player, id=self.kwargs['pk'], active=True)

	def get_context_data(self, **kwargs):
		context = super(ShowPlayer, self).get_context_data(**kwargs)
		player = self.object
		if (not player.human) and (player.user == self.request.user or player.game.status == 'finished'):
			try:
				my_kill = Kill.objects.filter(victim=player)[0]
				context['kill_tree'] = my_kill.get_descendants()
			except:
				pass
		return context

class Leaderboard(TemplateView):
	template_name = 'game/leaderboard.html'

	def get_context_data(self, **kwargs):
		context = super(Leaderboard, self).get_context_data(**kwargs)
		game = get_object_or_404(Game, id=self.kwargs['pk'])
		if game.status in ('in_progress', 'finished'):
			context['game'] = game
			context['top_humans'] = top_humans(game)
			context['top_zombies'] = top_zombies(game)
			return context
		else:
			raise Http404
