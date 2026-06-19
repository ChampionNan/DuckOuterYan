
SELECT
    a.name AS actor_name,
    t.title AS movie_title,
    ct.kind AS cast_type,
    p.info AS person_info,
    t.production_year,
    COUNT(DISTINCT k.keyword) AS keyword_count
FROM
    aka_name a
JOIN
    cast_info ci ON a.person_id = ci.person_id
JOIN
    title t ON ci.movie_id = t.id
JOIN
    movie_companies mc ON t.id = mc.movie_id
JOIN
    company_type ct ON mc.company_type_id = ct.id
JOIN
    person_info p ON a.person_id = p.person_id
LEFT JOIN
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN
    keyword k ON mk.keyword_id = k.id
JOIN
    comp_cast_type cc ON ci.person_role_id = cc.id
WHERE
    p.info_type_id = (SELECT id FROM info_type WHERE info = 'Birthdate')
    AND t.production_year > 2000
GROUP BY
    a.name, t.title, ct.kind, p.info, t.production_year;
