SELECT a.name AS actor_name, 
       t.title AS movie_title, 
       c.kind AS role_type, 
       m.info AS movie_info, 
       k.keyword AS movie_keyword
FROM aka_name a
JOIN cast_info ci ON a.person_id = ci.person_id
JOIN title t ON ci.movie_id = t.id
JOIN kind_type c ON t.kind_id = c.id
LEFT JOIN movie_info m ON t.id = m.movie_id AND m.info_type_id = (SELECT id FROM info_type WHERE info = 'Rating') 
LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN keyword k ON mk.keyword_id = k.id
WHERE a.name LIKE '%Smith%' 
  AND t.production_year >= 2000
  AND c.kind IN ('actor', 'actress');
