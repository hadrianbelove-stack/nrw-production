# {{ newsletter_title | default('NEW RELEASES WORTH WATCHING') }}

{{ date_range | default('Week of [DATE]') }} | {{ movie_count | default('X') }} Films

---

## Your Essay Here

[ESSAY PLACEHOLDER - Write your introduction here. This is where you share your thoughts on the week's releases, highlight trends, or provide context for your selections. Delete this placeholder text when done.]

---

## Featured Films

[FEATURED SECTION - Add 2-3 standout films from the Movie Bank below. Copy the entire movie block and paste it here.]

---

## The Rest

[THE REST - Add remaining films from the Movie Bank below. Copy each movie block and paste it here.]

---

## Movie Bank

Copy movie cards from below and paste into the sections above:

{% for movie in movies %}
---

### {{ movie.title }}{% if movie.year %} ({{ movie.year }}){% endif %}

{% if movie.is_virtual_screening and movie.screening_name %}**VIRTUAL SCREENING: {{ movie.screening_name }}{% if movie.screening_end_display %} · {{ movie.screening_end_display }}{% endif %}**{% endif %}

{% if movie.poster %}![{{ movie.title }} poster]({{ movie.poster }}){% endif %}

{% if movie.director or movie.runtime or movie.country %}**Director:** {{ movie.director | default('N/A') }} | **Runtime:** {{ movie.runtime | default('N/A') }}min | **Country:** {{ movie.country | default('N/A') }}{% endif %}

{% if movie.pull_quotes and movie.pull_quotes|length > 0 %}{% for pq in movie.pull_quotes %}
> *"{{ pq.text }}"* — {{ pq.critic }}, {{ pq.outlet }}
{% endfor %}{% endif %}
{% if movie.synopsis %}{{ movie.synopsis }}{% endif %}

{% if movie.streaming_services or movie.vod_services %}**Watch:** {% for service in movie.streaming_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% if movie.streaming_services and movie.vod_services %} | {% endif %}{% for service in movie.vod_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% endif %}

{% if movie.trailer_url or movie.wikipedia_url %}**More:** {% if movie.trailer_url %}[Trailer]({{ movie.trailer_url }}){% endif %}{% if movie.wikipedia_url %}{% if movie.trailer_url %} | {% endif %}[Wikipedia]({{ movie.wikipedia_url }}){% endif %}{% endif %}

{% if movie.rt_score %}**RT Score:** {{ movie.rt_score }}% &#127813;{% endif %}{% if movie.imdb_rating %} **IMDb:** {{ movie.imdb_rating }}{% endif %}

{% endfor %}

---

*New Releases Worth Watching - Curated new releases in theaters and on demand*
