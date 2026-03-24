# {{ newsletter_title | default('NEW RELEASES WORTH WATCHING') }}

{{ date_range | default('Week of [DATE]') }} | {{ movie_count | default(movies|length if movies else 'X') }} Films

---

{% if essay_content %}
{{ essay_content }}
{% else %}
## Your Essay Here

[ESSAY PLACEHOLDER - Write your introduction here. This is where you share your thoughts on the week's releases, highlight trends, or provide context for your selections. Delete this placeholder text when done.]
{% endif %}

---

{% if featured_movies %}
## Featured Films

*This week's standout releases*

{% for movie in featured_movies %}
### {{ movie.title }}{% if movie.year %} ({{ movie.year }}){% endif %}

{% if movie.poster %}![{{ movie.title }} poster]({{ movie.poster }}){% endif %}

{% if movie.director or movie.runtime or movie.country %}**Director:** {{ movie.director | default('N/A') }} | **Runtime:** {{ movie.runtime | default('N/A') }}min | **Country:** {{ movie.country | default('N/A') }}{% endif %}

{% if movie.rt_score %}**RT Score:** {{ movie.rt_score }}% &#127813;{% endif %}{% if movie.imdb_rating %} **IMDb:** {{ movie.imdb_rating }}{% endif %}

{% if movie.synopsis %}{{ movie.synopsis }}{% endif %}

{% if movie.streaming_services or movie.vod_services %}**Watch:** {% for service in movie.streaming_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% if movie.streaming_services and movie.vod_services %} | {% endif %}{% for service in movie.vod_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% endif %}

{% if movie.trailer_url or movie.rt_url or movie.wikipedia_url %}**More:** {% if movie.trailer_url %}[Trailer]({{ movie.trailer_url }}){% endif %}{% if movie.rt_url %}{% if movie.trailer_url %} | {% endif %}[RT]({{ movie.rt_url }}){% endif %}{% if movie.wikipedia_url %}{% if movie.trailer_url or movie.rt_url %} | {% endif %}[Wikipedia]({{ movie.wikipedia_url }}){% endif %}{% endif %}

---

{% endfor %}
{% endif %}

{% if rest_movies %}
## The Rest

*More new releases worth your time*

{% for movie in rest_movies %}
### {{ movie.title }}{% if movie.year %} ({{ movie.year }}){% endif %}

{% if movie.poster %}![{{ movie.title }} poster]({{ movie.poster }}){% endif %}

{% if movie.director or movie.runtime or movie.country %}**Director:** {{ movie.director | default('N/A') }} | **Runtime:** {{ movie.runtime | default('N/A') }}min | **Country:** {{ movie.country | default('N/A') }}{% endif %}

{% if movie.rt_score %}**RT Score:** {{ movie.rt_score }}% &#127813;{% endif %}{% if movie.imdb_rating %} **IMDb:** {{ movie.imdb_rating }}{% endif %}

{% if movie.synopsis %}{{ movie.synopsis }}{% endif %}

{% if movie.streaming_services or movie.vod_services %}**Watch:** {% for service in movie.streaming_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% if movie.streaming_services and movie.vod_services %} | {% endif %}{% for service in movie.vod_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% endif %}

{% if movie.trailer_url or movie.rt_url or movie.wikipedia_url %}**More:** {% if movie.trailer_url %}[Trailer]({{ movie.trailer_url }}){% endif %}{% if movie.rt_url %}{% if movie.trailer_url %} | {% endif %}[RT]({{ movie.rt_url }}){% endif %}{% if movie.wikipedia_url %}{% if movie.trailer_url or movie.rt_url %} | {% endif %}[Wikipedia]({{ movie.wikipedia_url }}){% endif %}{% endif %}

---

{% endfor %}
{% endif %}

{% if movies and not featured_movies and not rest_movies %}
## This Week's Releases

*New films worth your time*

{% for movie in movies %}
### {{ movie.title }}{% if movie.year %} ({{ movie.year }}){% endif %}

{% if movie.poster %}![{{ movie.title }} poster]({{ movie.poster }}){% endif %}

{% if movie.director or movie.runtime or movie.country %}**Director:** {{ movie.director | default('N/A') }} | **Runtime:** {{ movie.runtime | default('N/A') }}min | **Country:** {{ movie.country | default('N/A') }}{% endif %}

{% if movie.rt_score %}**RT Score:** {{ movie.rt_score }}% &#127813;{% endif %}{% if movie.imdb_rating %} **IMDb:** {{ movie.imdb_rating }}{% endif %}

{% if movie.synopsis %}{{ movie.synopsis }}{% endif %}

{% if movie.streaming_services or movie.vod_services %}**Watch:** {% for service in movie.streaming_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% if movie.streaming_services and movie.vod_services %} | {% endif %}{% for service in movie.vod_services %}[{{ service.name }}]({{ service.url }}){% if not loop.last %} | {% endif %}{% endfor %}{% endif %}

{% if movie.trailer_url or movie.rt_url or movie.wikipedia_url %}**More:** {% if movie.trailer_url %}[Trailer]({{ movie.trailer_url }}){% endif %}{% if movie.rt_url %}{% if movie.trailer_url %} | {% endif %}[RT]({{ movie.rt_url }}){% endif %}{% if movie.wikipedia_url %}{% if movie.trailer_url or movie.rt_url %} | {% endif %}[Wikipedia]({{ movie.wikipedia_url }}){% endif %}{% endif %}

---

{% endfor %}
{% endif %}

*New Releases Worth Watching - Curated new releases in theaters and on demand*
