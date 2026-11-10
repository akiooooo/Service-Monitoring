# Подготовленные улучшения

Ветка [prepared-improvements](https://github.com/akiooooo/Service-Monitoring/tree/prepared-improvements) содержит 100 реальных коммитов, подготовленных заранее. Большинство изменений расширяет регрессионные тесты; отдельные шаги исправляют обнаруженные дефекты. Это не 100 новых возможностей приложения.

Каждый шаг добавляет самостоятельный проверяемый сценарий. Все 100 сценариев вместе с исходными тестами прошли проверку; отдельно проверялся каждый добавляемый тест в соответствующей версии кода. Названия и состав изменений приведены ниже. Номер соответствует методу `test_NNN` в `tests/test_prepared_regressions.py`.

## Публикация

Каждый московский календарный день для каждого репозитория выбираются **от 1 до 4 публикаций** и соответствующее число разных часов в диапазоне 09:00–22:59. В выбранный час запуск дополнительно смещается на случайное число секунд: номинально публикация начинается между :07 и :17. Часы и секунды меняются по дням и отличаются между репозиториями. План воспроизводится из даты и имени репозитория, поэтому повторные запуски не меняют дневную норму.

Workflow проверяет план раз в час с 09:07 до 22:07 по Москве; в невыбранные часы он завершается без изменения файлов. В выбранный час ожидается запланированное время (не более 10 минут), обновляется main и выполняется следующий патч с тестами. После 23:00 автоматическая публикация запрещена, в том числе если GitHub задержал запуск. Время самого коммита дополнительно зависит от длительности проверок. Ручные публикации также расходуют дневной лимит, а `check_only` его не расходует. Уже обработанный час повторно не используется.

GitHub Actions может задерживать запуски и пропускать их при высокой нагрузке; пропущенные шаги не догоняются массово. Поэтому 1–4 — выбранный план на день, а при сбое фактических публикаций может оказаться меньше. Исходные коммиты перечислены в таблице ниже; номер применённого шага сохраняется в состоянии очереди.

Перед публикацией проверяются хеш патча, родитель, название и список файлов, затем выполняется полный набор тестов проекта. Ошибка тестов, конфликт, изменение рабочей копии или отказ push прерывают запуск. Принудительная отправка и автоматическое разрешение конфликтов не используются. После 100 шагов новых коммитов не будет.

Очередь: `.ghostcommit/queue.json`; состояние: `.ghostcommit/state.json`; исполнитель: `scripts/publish_prepared.py`. Изменять счётчик вручную нельзя — порядок зависит от предыдущих патчей. Текущая ветка `main` может содержать пользовательские изменения: если они конфликтуют с очередью, потребуется вручную проверить и пересобрать оставшиеся патчи.

Для ручной проверки откройте **Actions → Проверенные изменения по расписанию → Run workflow**. Флажок `check_only` проверяет следующий патч без публикации. Без флажка применяется один шаг с тестами. Локально `python scripts/publish_prepared.py --check-only` только проверяет; команда без флага создаёт и отправляет коммит, поэтому её следует запускать в отдельной чистой копии.

Для остановки выберите **Disable workflow** в меню Actions. Токены в коде и локальной панели отсутствуют: workflow использует временный `GITHUB_TOKEN` с правом `contents: write`. Публикация через этот токен не запускает другие workflows на push, поэтому тесты выполняются непосредственно перед отправкой. Дополнительный PAT не требуется.

Защита очереди проверяется командой `python -m unittest discover -s .ghostcommit -p test_queue_worker.py -q`. Тесты используют временные локальные репозитории, без обращений к GitHub.

## Состав очереди

| № | Изменение | Исходный коммит |
|---|---|---|
| 1 | Исправлена блокировка проверок при ошибке базы | [37a3d39](https://github.com/akiooooo/Service-Monitoring/commit/37a3d39ea00dab51002a5115589fce4cab0f348e) |
| 2 | Тест запроса с массивом вместо объекта | [a27bcc1](https://github.com/akiooooo/Service-Monitoring/commit/a27bcc1eaba69ba2ed2aeb0a3d97794b878688a7) |
| 3 | Тест запроса со строкой вместо объекта | [9ddf3b5](https://github.com/akiooooo/Service-Monitoring/commit/9ddf3b5f5280674feeb4526d007acce071c0fd5b) |
| 4 | Тест запроса с числом вместо объекта | [e19e41d](https://github.com/akiooooo/Service-Monitoring/commit/e19e41d4975199217a8eaaf1427003e9f44cbd20) |
| 5 | Тест запроса с логическим значением | [e279d35](https://github.com/akiooooo/Service-Monitoring/commit/e279d35664f6de65f4ecb369eb82ab70dd4567b3) |
| 6 | Проверка обязательного имени сервиса | [47664e8](https://github.com/akiooooo/Service-Monitoring/commit/47664e80b03439ed6a1524836f95b05ee8ec1242) |
| 7 | Проверка обязательного адреса сервиса | [9dc2b00](https://github.com/akiooooo/Service-Monitoring/commit/9dc2b000f7cf36af2d76254e839e5741ef11373b) |
| 8 | Тест имени из пробелов | [26c5d47](https://github.com/akiooooo/Service-Monitoring/commit/26c5d473dde576c4409d6cbedf3c87e9204e1fcd) |
| 9 | Проверка длины имени сервиса | [dad2bdc](https://github.com/akiooooo/Service-Monitoring/commit/dad2bdc5b4f36dda48e5a15e39a6ecd9430a6997) |
| 10 | Тест пустой категории | [eccd548](https://github.com/akiooooo/Service-Monitoring/commit/eccd5486c44d4fea3fa721f153458cb94ff6eb84) |
| 11 | Проверка длины категории | [43b6cb0](https://github.com/akiooooo/Service-Monitoring/commit/43b6cb052c53b0bc917d1a7a4b601e0758f9c50a) |
| 12 | Тест числового имени сервиса | [178fd7c](https://github.com/akiooooo/Service-Monitoring/commit/178fd7c562f326bbefb9a9ad05b670b8fa9cb3d0) |
| 13 | Тест категории с неверным типом | [d53a779](https://github.com/akiooooo/Service-Monitoring/commit/d53a7797946a3445c1388f43501a1a62dfbcfac1) |
| 14 | Тест адреса со значением null | [f51a7d2](https://github.com/akiooooo/Service-Monitoring/commit/f51a7d2f7364588e7b433eac92bf6f8d2a2d21d6) |
| 15 | Проверка длины адреса сервиса | [e7dc708](https://github.com/akiooooo/Service-Monitoring/commit/e7dc708e7fa59674e45e8f06fbfa5e3d104ff420) |
| 16 | Тест неподдерживаемого протокола FTP | [46c949d](https://github.com/akiooooo/Service-Monitoring/commit/46c949d19454a14161203ed65b996234b3f56d58) |
| 17 | Запрет локальных файлов в адресе сервиса | [9b2464e](https://github.com/akiooooo/Service-Monitoring/commit/9b2464e8c80be4553134d7e81cb772d6fefab66b) |
| 18 | Тест адреса с паролем | [d953915](https://github.com/akiooooo/Service-Monitoring/commit/d9539153531470f3c435207a62e2c809dce38026) |
| 19 | Тест адреса с именем пользователя | [e183be3](https://github.com/akiooooo/Service-Monitoring/commit/e183be30ec8785e11f0930128a5b689fa2b1c5d0) |
| 20 | Проверка фрагмента в адресе сервиса | [e7715d6](https://github.com/akiooooo/Service-Monitoring/commit/e7715d6aee241d42f4349f7ffa7adfea41337f31) |
| 21 | Проверка верхней границы порта | [f24b2c2](https://github.com/akiooooo/Service-Monitoring/commit/f24b2c21e77616f67ab42ca0cdd01334b52117ce) |
| 22 | Тест нечислового порта | [3a1b706](https://github.com/akiooooo/Service-Monitoring/commit/3a1b7069ca5cfa84b9530ac0a92164333b1aa7de) |
| 23 | Тест адреса без хоста | [eba0ec2](https://github.com/akiooooo/Service-Monitoring/commit/eba0ec2a0d28e74d3c48ee0c906219e60616d7e7) |
| 24 | Проверка домена с кириллицей | [a483099](https://github.com/akiooooo/Service-Monitoring/commit/a48309923750c5bcc550745c370c86595d6c1356) |
| 25 | Тест пробела в адресе | [ea6ab53](https://github.com/akiooooo/Service-Monitoring/commit/ea6ab53b680943b6199e88a4439a514b7a68badc) |
| 26 | Проверка минимального интервала | [419d74f](https://github.com/akiooooo/Service-Monitoring/commit/419d74f5990babf5406fc4829dc321ea151fbd98) |
| 27 | Проверка максимального интервала | [fe7b1c6](https://github.com/akiooooo/Service-Monitoring/commit/fe7b1c68a8678ded0b24d71a1c9ae5581424b2c4) |
| 28 | Тест нулевого таймаута | [665a0b7](https://github.com/akiooooo/Service-Monitoring/commit/665a0b7c81da575b17b79a8b4c9dfbdbe45a561f) |
| 29 | Проверка максимального таймаута | [f6cc46f](https://github.com/akiooooo/Service-Monitoring/commit/f6cc46f6b7ab3c8527811f3c9d2c4536521c00c9) |
| 30 | Проверка нижней границы HTTP-кода | [94c2414](https://github.com/akiooooo/Service-Monitoring/commit/94c2414cf38ea91a91400ea19a582e493abaa8c2) |
| 31 | Проверка верхней границы HTTP-кода | [53d8490](https://github.com/akiooooo/Service-Monitoring/commit/53d8490cde4edd24e6a1fb7d5bad87ca27b6c3d7) |
| 32 | Тест логического значения интервала | [0639527](https://github.com/akiooooo/Service-Monitoring/commit/063952799a48ab88c317c9ea26a79a65e7e67148) |
| 33 | Тест дробного таймаута | [163a764](https://github.com/akiooooo/Service-Monitoring/commit/163a764051bc4b14aa50f969b15d69f90f3a78e0) |
| 34 | Тест HTTP-кода в строковом формате | [1ec8db6](https://github.com/akiooooo/Service-Monitoring/commit/1ec8db6bd9c581a6b87cbe864104bcf4e442f802) |
| 35 | Тест строкового значения паузы | [6e698d3](https://github.com/akiooooo/Service-Monitoring/commit/6e698d308f63ef1c99e7fb32696d2332a3381640) |
| 36 | Граничные значения настроек сервиса | [e3557df](https://github.com/akiooooo/Service-Monitoring/commit/e3557df2563c944d960996470a979ebbaeccc981) |
| 37 | Удаление пробелов в настройках сервиса | [177e5a0](https://github.com/akiooooo/Service-Monitoring/commit/177e5a0e92b69933f9b50177b4ea84f37888b09e) |
| 38 | Проверка настроек по умолчанию | [2aa92a3](https://github.com/akiooooo/Service-Monitoring/commit/2aa92a33d31f992523f6c764cabe1ac3f746ed51) |
| 39 | Тест адреса с punycode и параметрами | [ce74e8d](https://github.com/akiooooo/Service-Monitoring/commit/ce74e8dda9fb93718bd5c5adcd990ce0e5f1b7c8) |
| 40 | Тест проверки с интервалом в сутки | [229e82a](https://github.com/akiooooo/Service-Monitoring/commit/229e82a5d5070eec6c476e404d5590cc9bd8a68d) |
| 41 | Проверка служебного health endpoint | [4c41012](https://github.com/akiooooo/Service-Monitoring/commit/4c41012c0a75951241e96ceff7a7e054224b55d2) |
| 42 | Список сервисов в пустой базе | [56b4abc](https://github.com/akiooooo/Service-Monitoring/commit/56b4abc56ee83872b2f7357654cea587efc66fe0) |
| 43 | Тест создания сервиса через API | [8d403d6](https://github.com/akiooooo/Service-Monitoring/commit/8d403d6a99e6c9d6508f3800aa3c5eb4ca0d735b) |
| 44 | Получение настроек отдельного сервиса | [f98d55a](https://github.com/akiooooo/Service-Monitoring/commit/f98d55a36551e2778bc8a72c6f51ce9ba317e569) |
| 45 | Тест запроса неизвестного сервиса | [6471562](https://github.com/akiooooo/Service-Monitoring/commit/64715625f395345e634ee731dae7778a850cf3f2) |
| 46 | Тест нечислового идентификатора | [47db6ef](https://github.com/akiooooo/Service-Monitoring/commit/47db6ef11e88c4f2bc20ec5ba8c6d7997eeaa6c0) |
| 47 | Тест истории с отрицательным идентификатором | [38c768e](https://github.com/akiooooo/Service-Monitoring/commit/38c768edef21e86770cb70c34e2d2332bdd4d2d4) |
| 48 | Тест неизвестного маршрута API | [d537b9c](https://github.com/akiooooo/Service-Monitoring/commit/d537b9cc76fa17d71ceb5863d58395c27480dc78) |
| 49 | Тест нулевого периода отчёта | [f9ce51f](https://github.com/akiooooo/Service-Monitoring/commit/f9ce51f75e4c6df0e7965417b7e4c22cade4b846) |
| 50 | Тест периода отчёта больше месяца | [18ba474](https://github.com/akiooooo/Service-Monitoring/commit/18ba47448edc95aac7cabf7ce65eaee3560556d4) |
| 51 | Тест текстового периода отчёта | [d8b1860](https://github.com/akiooooo/Service-Monitoring/commit/d8b186074791236340769a85eacb1fe47139b756) |
| 52 | Тест дробного периода отчёта | [5fbbbbe](https://github.com/akiooooo/Service-Monitoring/commit/5fbbbbea896f601a7c6391aa3664156639b021e3) |
| 53 | Проверка отчёта за 720 часов | [164a2cc](https://github.com/akiooooo/Service-Monitoring/commit/164a2cccd43a5605f37b356bcb362c644e36485a) |
| 54 | Тест записи с чужого сайта | [bae214f](https://github.com/akiooooo/Service-Monitoring/commit/bae214f3d02e4b464bcad4f569b718117dcb3f42) |
| 55 | Запрет создания сервиса через HTML-форму | [d609878](https://github.com/akiooooo/Service-Monitoring/commit/d609878854c06a1e8380f6f86c3800aaf9f40e13) |
| 56 | Обработка повреждённого JSON | [96b2757](https://github.com/akiooooo/Service-Monitoring/commit/96b275715248d97301f3f8489cd27f19bac465d8) |
| 57 | Проверка ограничения размера запроса | [ba21d27](https://github.com/akiooooo/Service-Monitoring/commit/ba21d277991c0f011e1f22588b8bbbc288079f12) |
| 58 | Тест создания сервиса из массива | [8a960fc](https://github.com/akiooooo/Service-Monitoring/commit/8a960fce6d9542599f01a63442525124ddef2682) |
| 59 | Сброс расписания при редактировании | [fd5cab9](https://github.com/akiooooo/Service-Monitoring/commit/fd5cab94212f009d0e1ee6c5c930fa920e0f9c40) |
| 60 | Сохранение настроек при ошибке редактирования | [6acb1a7](https://github.com/akiooooo/Service-Monitoring/commit/6acb1a75e39ab578f802f9c6a388b82c2e11aed5) |
| 61 | Тест ручного запуска проверки | [641bd7b](https://github.com/akiooooo/Service-Monitoring/commit/641bd7b71b323f386151ce1ae59cc1afaa59cfb0) |
| 62 | Тест повторного запуска занятой проверки | [2e7493e](https://github.com/akiooooo/Service-Monitoring/commit/2e7493ef7317c85b1920ce379da52a6a996272ba) |
| 63 | Статус сервиса до первой проверки | [7aa78c1](https://github.com/akiooooo/Service-Monitoring/commit/7aa78c12e25dcff18a1ed8b211c280bef6d86a49) |
| 64 | Статус сервиса после успешного ответа | [7e72dc0](https://github.com/akiooooo/Service-Monitoring/commit/7e72dc0ca9254da4cc542f3bd55d14491f4a58be) |
| 65 | Статус сервиса после ошибки | [8fefe88](https://github.com/akiooooo/Service-Monitoring/commit/8fefe8867ff184f9746bed63ef592db7b4e50a7b) |
| 66 | Пауза имеет приоритет над результатом проверки | [2e557fb](https://github.com/akiooooo/Service-Monitoring/commit/2e557fb0ecc532783867eac0b143b62e00776b30) |
| 67 | Поиск по адресу без учёта регистра | [0b19d87](https://github.com/akiooooo/Service-Monitoring/commit/0b19d87d822e3e8ed8ff0d3c181f582be66ffb09) |
| 68 | Фильтр сервисов по категории | [e0425ed](https://github.com/akiooooo/Service-Monitoring/commit/e0425ed01c369ba72b59f75be339b41b32b811f2) |
| 69 | Тест расчёта доступности | [274fd83](https://github.com/akiooooo/Service-Monitoring/commit/274fd83aa1592829e714d67e7534aa66ad914423) |
| 70 | Тест среднего времени отклика | [1f70c04](https://github.com/akiooooo/Service-Monitoring/commit/1f70c04a30f92b36764462548917d4697e81e269) |
| 71 | Изоляция истории разных сервисов | [331db84](https://github.com/akiooooo/Service-Monitoring/commit/331db840128a2f9fdd27bda251de245d5b35e460) |
| 72 | Ограничение размера истории проверок | [8fa81b3](https://github.com/akiooooo/Service-Monitoring/commit/8fa81b3b650960dd9e55b57dd3f1bbda16a4a7b4) |
| 73 | Проверка формата CSV-отчёта | [811a8c6](https://github.com/akiooooo/Service-Monitoring/commit/811a8c6a4b722c1ddb6148ab966eab23f711b5b1) |
| 74 | Защитные заголовки в ответах API | [f5fdc22](https://github.com/akiooooo/Service-Monitoring/commit/f5fdc226c699163920439edcef1aa212bbf2225c) |
| 75 | Запрет доступа к исходникам через HTTP | [2ad353d](https://github.com/akiooooo/Service-Monitoring/commit/2ad353dd1f40ac5bf92e40b3200be2840da9b334) |
| 76 | Результат удалённого сервиса не сохраняется | [29d4e38](https://github.com/akiooooo/Service-Monitoring/commit/29d4e3899a140f9d15d82b1f297d9ff82a45f87f) |
| 77 | Открытие инцидента при первом сбое | [8c6a193](https://github.com/akiooooo/Service-Monitoring/commit/8c6a193f00d8a2db2fb452481520e4faf6a5b205) |
| 78 | Повторные ошибки не дублируют инцидент | [cfb455e](https://github.com/akiooooo/Service-Monitoring/commit/cfb455eff38b930acaff6cb2925372178fb408cf) |
| 79 | Закрытие инцидента после восстановления | [c43b717](https://github.com/akiooooo/Service-Monitoring/commit/c43b717c2805a2c405f63037981b054d0c9197ec) |
| 80 | Успешные проверки не создают инцидентов | [5c5e891](https://github.com/akiooooo/Service-Monitoring/commit/5c5e891720a49dcc0326ea1e4835dbcb18dfa3a0) |
| 81 | Новый инцидент после повторного сбоя | [b764a12](https://github.com/akiooooo/Service-Monitoring/commit/b764a128189ce27efc8266533cb6b1bb0f2cb555) |
| 82 | Изоляция инцидентов разных сервисов | [95ff355](https://github.com/akiooooo/Service-Monitoring/commit/95ff35563fac5aac546ac22df206a87a5374f74d) |
| 83 | Сохранение первоначальной причины сбоя | [3d203af](https://github.com/akiooooo/Service-Monitoring/commit/3d203af85aca75f5f74ac5a3098c742cbc01a99a) |
| 84 | Причина сбоя при пустом сообщении | [ce290b3](https://github.com/akiooooo/Service-Monitoring/commit/ce290b33bc60c5c7f556f42e4c948c50a9d4ea19) |
| 85 | Таймаут без HTTP-кода в истории | [ba03997](https://github.com/akiooooo/Service-Monitoring/commit/ba0399702174287771adb8d7a0c5b21964beade9) |
| 86 | Сохранение дробного времени отклика | [78541a2](https://github.com/akiooooo/Service-Monitoring/commit/78541a2563abbc529643c2538a08431d6be96f22) |
| 87 | Чтение истории после открытия базы заново | [bc91752](https://github.com/akiooooo/Service-Monitoring/commit/bc917520e3fabf09e49e6d174a1752ca58e7a0df) |
| 88 | Откат транзакции при ошибке | [be98939](https://github.com/akiooooo/Service-Monitoring/commit/be98939b8b28a73acfc527c72ad5116cf6e81355) |
| 89 | Проверка внешних ключей истории | [3f7f699](https://github.com/akiooooo/Service-Monitoring/commit/3f7f69997f595cbee80f5592c4684f5aaa780796) |
| 90 | Удаление истории вместе с сервисом | [7ef2e17](https://github.com/akiooooo/Service-Monitoring/commit/7ef2e178b976f64455ad2903c71dcdc1322ad21d) |
| 91 | Удаление сервиса не затрагивает соседний | [3cb14ee](https://github.com/akiooooo/Service-Monitoring/commit/3cb14eeadbf4a284a7a2f636774635f56329731e) |
| 92 | Защита CSV от формул со знаком равенства | [e7c02ad](https://github.com/akiooooo/Service-Monitoring/commit/e7c02ad29cb10cab04d4b5914d8f7a34030d2265) |
| 93 | Защита CSV от формул со знаком плюс | [11d557a](https://github.com/akiooooo/Service-Monitoring/commit/11d557a5ac5ad4d67f88c9f569dbe2632412dd4f) |
| 94 | Защита CSV от формул со знаком минус | [167887e](https://github.com/akiooooo/Service-Monitoring/commit/167887e582329d7082de134349ac5c7cd370877c) |
| 95 | Защита CSV от формул с символом @ | [521c839](https://github.com/akiooooo/Service-Monitoring/commit/521c8399f89a91736324e5c446a8dfd65d61fd6b) |
| 96 | Экранирование разделителя в CSV | [79fffc3](https://github.com/akiooooo/Service-Monitoring/commit/79fffc3cf04805bca6ff754dae6f81e55c826db3) |
| 97 | Старые проверки не попадают в текущую статистику | [6d8b703](https://github.com/akiooooo/Service-Monitoring/commit/6d8b70330dd1b0349dffa26a715fd48744048652) |
| 98 | Открытый инцидент остаётся виден за выбранный период | [d3e7d74](https://github.com/akiooooo/Service-Monitoring/commit/d3e7d74df68f4178afffbc30b02ef34d9a543cf8) |
| 99 | Скрытие давно закрытых инцидентов | [8997faf](https://github.com/akiooooo/Service-Monitoring/commit/8997fafc5a223574c064c645a8ed17963ac593b5) |
| 100 | Пустая история нового сервиса | [9a770c7](https://github.com/akiooooo/Service-Monitoring/commit/9a770c7b314f13c913c2dff3607f4af6fcfa6814) |
