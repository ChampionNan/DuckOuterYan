SELECT
    a.name AS actor_name,
    t.title AS movie_title,
    c.nr_order AS cast_order,
    m.name AS company_name,
    k.keyword AS movie_keyword,
    i.info AS movie_info
FROM
    aka_name a
JOIN
    cast_info c ON a.person_id = c.person_id
JOIN
    title t ON c.movie_id = t.id
JOIN
    movie_companies mc ON t.id = mc.movie_id
JOIN
    company_name m ON mc.company_id = m.id
LEFT JOIN
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN
    keyword k ON mk.keyword_id = k.id
LEFT JOIN
    movie_info mi ON t.id = mi.movie_id
LEFT JOIN
    info_type i ON mi.info_type_id = i.id
WHERE
    a.name IS NOT NULL
    AND t.production_year >= 2000
    AND m.country_code = 'USA';
