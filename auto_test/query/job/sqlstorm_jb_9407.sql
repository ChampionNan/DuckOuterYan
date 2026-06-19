SELECT
    a.name AS aka_name,
    t.title AS movie_title,
    c.nr_order AS cast_order,
    rc.role AS role_name,
    cmp.name AS company_name,
    k.keyword AS movie_keyword,
    mi.info AS movie_info
FROM
    aka_name a
JOIN
    cast_info c ON a.person_id = c.person_id
JOIN
    title t ON c.movie_id = t.id
JOIN
    role_type rc ON c.role_id = rc.id
JOIN
    movie_companies mc ON t.id = mc.movie_id
JOIN
    company_name cmp ON mc.company_id = cmp.id
LEFT JOIN
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN
    keyword k ON mk.keyword_id = k.id
LEFT JOIN
    movie_info mi ON t.id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Summary')
WHERE
    t.production_year BETWEEN 2000 AND 2020
AND
    cmp.country_code = 'USA';
