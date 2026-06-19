SELECT
    t.title,
    a.name AS actor_name,
    c.kind AS cast_type,
    co.name AS company_name,
    kt.keyword AS movie_keyword,
    ti.info AS movie_info,
    COUNT(*) AS total_cast
FROM
    title t
JOIN
    cast_info ci ON t.id = ci.movie_id
JOIN
    aka_name a ON ci.person_id = a.person_id
JOIN
    comp_cast_type c ON ci.person_role_id = c.id
JOIN
    movie_companies mc ON t.id = mc.movie_id
JOIN
    company_name co ON mc.company_id = co.id
JOIN
    movie_keyword mk ON t.id = mk.movie_id
JOIN
    keyword kt ON mk.keyword_id = kt.id
LEFT JOIN
    movie_info mi ON t.id = mi.movie_id
LEFT JOIN
    info_type ti ON mi.info_type_id = ti.id
WHERE
    t.production_year > 2000
    AND co.country_code = 'USA'
GROUP BY
    t.title, a.name, c.kind, co.name, kt.keyword, ti.info;
