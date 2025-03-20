-- 删除所有引用 thepaper-selenium 的记录
DELETE FROM source_stats WHERE source_id = 'thepaper-selenium';
DELETE FROM source_aliases WHERE source_id = 'thepaper-selenium';
DELETE FROM news WHERE source_id = 'thepaper-selenium';
-- 最后删除源记录
DELETE FROM sources WHERE id = 'thepaper-selenium';

-- 确认删除成功
SELECT id, name, active FROM sources WHERE id LIKE '%thepaper%'; 