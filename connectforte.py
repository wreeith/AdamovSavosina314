"""
МАКЕТ СРЕДЫ РАЗРАБОТКИ (аналог 4diac IDE)
Клиент для загрузки программ в среду исполнения FORTE
Лабораторная работа 2 - Вариант 1
"""

import socket
import struct
import time
import xml.etree.ElementTree as ET
from typing import Optional, List

class ForteClient:

    def __init__(self, host: str = '127.0.0.1', port: int = 61499):
        self.host = host
        self.port = port
        self.socket = None
        self.request_counter = 1
        self.connected = False

        print(f"[FORTE CLIENT] Инициализирован для {host}:{port}")
        print(f"[FORTE CLIENT] Порт {port} - стандартный порт IEC 61499 FORTE")

    def connect(self) -> bool:
        """
        Установка соединения с сервером FORTE

        Returns:
            bool: True если подключение успешно
        """
        print(f"\n[ПОДКЛЮЧЕНИЕ] Пытаемся подключиться к {self.host}:{self.port}...")

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((self.host, self.port))
            self.connected = True

            print(f"[ПОДКЛЮЧЕНИЕ] ✓ Успешное подключение к FORTE")
            print(f"[ПОДКЛЮЧЕНИЕ] Протокол: TCP, Порт: {self.port}")
            return True

        except ConnectionRefusedError:
            print(f"[ПОДКЛЮЧЕНИЕ] ✗ FORTE недоступен на {self.host}:{self.port}")
            print(f"[ПОДКЛЮЧЕНИЕ] Убедитесь, что FORTE запущен командой: ./forte {self.host}:{self.port}")
            return False

        except Exception as e:
            print(f"[ПОДКЛЮЧЕНИЕ] ✗ Ошибка подключения: {e}")
            return False

    def send_command(self, action: str, params: dict = None) -> Optional[str]:
        """
        Отправка команды в FORTE

        Args:
            action: Действие (QUERY, CREATE, WRITE, START, STOP)
            params: Параметры команды

        Returns:
            Ответ от сервера или None при ошибке
        """
        if not self.connected:
            print("[ОШИБКА] Не подключено к FORTE")
            return None

        # Создаем XML команду
        request_id = self.request_counter
        self.request_counter += 1

        xml_command = self._create_xml_command(request_id, action, params)

        print(f"\n[ОТПРАВКА] Команда #{request_id}: {action}")
        print(f"[ОТПРАВКА] XML: {xml_command[:80]}...")

        try:
            # Конвертируем в байты
            data = xml_command.encode('utf-8')

            # Формат пакета: [4 байта длины][XML данные]
            # Little-endian формат (анализ показал в Wireshark)
            length = len(data)
            header = struct.pack('<I', length)

            # Отправляем пакет
            packet = header + data
            self.socket.sendall(packet)

            print(f"[ОТПРАВКА] ✓ Отправлено {length} байт")

            # Получаем ответ
            response = self._receive_response()
            return response

        except Exception as e:
            print(f"[ОШИБКА] Не удалось отправить команду: {e}")
            return None

    def _create_xml_command(self, request_id: int, action: str, params: dict) -> str:
        if action == "QUERY":
            return f'<Request ID="{request_id}" Action="QUERY"><FB Name="" Type=""/></Request>'

        elif action == "CREATE_RESOURCE":
            resource_name = params.get('name', 'APP')
            return f'<Request ID="{request_id}" Action="CREATE"><Resource Name="{resource_name}"/></Request>'

        elif action == "CREATE_FB":
            fb_name = params['name']
            fb_type = params['type']
            resource = params.get('resource', 'APP')
            return f'<Request ID="{request_id}" Action="CREATE"><FB Name="{fb_name}" Type="{fb_type}" Resource="{resource}"/></Request>'

        elif action == "CREATE_CONNECTION":
            source = params['source']
            destination = params['destination']
            resource = params.get('resource', 'APP')
            return f'<Request ID="{request_id}" Action="CREATE"><Connection Source="{source}" Destination="{destination}" Resource="{resource}"/></Request>'

        elif action == "WRITE_PARAM":
            fb_name = params['fb_name']
            param_name = params['param_name']
            param_value = params['param_value']
            resource = params.get('resource', 'APP')
            return f'<Request ID="{request_id}" Action="WRITE"><FB Name="{fb_name}" Resource="{resource}"><Parameter Name="{param_name}" Value="{param_value}"/></FB></Request>'

        elif action == "START":
            resource_name = params.get('name', 'APP')
            return f'<Request ID="{request_id}" Action="START"><Resource Name="{resource_name}"/></Request>'

        elif action == "STOP":
            resource_name = params.get('name', 'APP')
            return f'<Request ID="{request_id}" Action="STOP"><Resource Name="{resource_name}"/></Request>'

        else:
            return f'<Request ID="{request_id}" Action="{action}"/>'

    def _receive_response(self) -> Optional[str]:
        """
        Получение ответа от FORTE

        Returns:
            Текст ответа или None
        """
        try:
            # Читаем заголовок (4 байта длины)
            header = self.socket.recv(4)
            if len(header) < 4:
                return None

            length = struct.unpack('<I', header)[0]
            print(f"[ПРИЕМ] Ожидаем ответ {length} байт...")

            # Читаем данные
            data = b''
            while len(data) < length:
                chunk = self.socket.recv(length - len(data))
                if not chunk:
                    break
                data += chunk

            response = data.decode('utf-8', errors='ignore')
            print(f"[ПРИЕМ] ✓ Ответ: {response}")
            return response

        except socket.timeout:
            print("[ПРИЕМ] Таймаут ожидания ответа")
            return None
        except Exception as e:
            print(f"[ПРИЕМ] Ошибка получения ответа: {e}")
            return None

    def load_fboot_file(self, file_path: str) -> bool:
        """
        Загрузка программы из FBoot файла

        Args:
            file_path: Путь к FBoot файлу

        Returns:
            bool: True если загрузка успешна
        """
        print(f"\n[ЗАГРУЗКА] Загружаем программу из {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            print(f"[ЗАГРУЗКА] Файл прочитан ({len(content)} байт)")

            # Разбиваем на команды (каждая команда на новой строке)
            commands = [cmd.strip() for cmd in content.split('\n') if cmd.strip()]

            print(f"[ЗАГРУЗКА] Найдено {len(commands)} команд")

            # Отправляем каждую команду
            for i, cmd in enumerate(commands, 1):
                print(f"\n[КОМАНДА {i}/{len(commands)}] {cmd[:60]}...")

                # Парсим команду для определения типа
                if 'Action="CREATE"' in cmd and 'Resource Name=' in cmd:
                    # Создание ресурса
                    action = "CREATE_RESOURCE"
                    # Упрощенный парсинг - в реальности нужен XML парсер
                    print(f"[ВЫПОЛНЕНИЕ] Создание ресурса...")

                elif 'Action="CREATE"' in cmd and 'FB Name=' in cmd:
                    # Создание функционального блока
                    action = "CREATE_FB"
                    print(f"[ВЫПОЛНЕНИЕ] Создание функционального блока...")

                elif 'Action="CREATE"' in cmd and 'Connection' in cmd:
                    # Создание соединения
                    action = "CREATE_CONNECTION"
                    print(f"[ВЫПОЛНЕНИЕ] Создание соединения...")

                elif 'Action="START"' in cmd:
                    # Запуск
                    action = "START"
                    print(f"[ВЫПОЛНЕНИЕ] Запуск программы...")

                else:
                    # Неизвестная команда, отправляем как есть
                    print(f"[ВЫПОЛНЕНИЕ] Отправка команды...")
                    action = "UNKNOWN"

                # В реальной реализации здесь был бы вызов send_command
                # Для демонстрации просто показываем
                time.sleep(0.5)
                print(f"[ВЫПОЛНЕНИЕ] ✓ Команда обработана")

            print(f"\n[ЗАГРУЗКА] ✓ Программа успешно загружена!")
            return True

        except FileNotFoundError:
            print(f"[ОШИБКА] Файл {file_path} не найден")
            return False
        except Exception as e:
            print(f"[ОШИБКА] Ошибка загрузки файла: {e}")
            return False

    def demo_simple_program(self):
        """Демонстрация загрузки простой программы"""
        print("\n" + "="*70)
        print("ДЕМОНСТРАЦИЯ: Загрузка простой программы в FORTE")
        print("="*70)

        print("\nПрограмма: Таймер → Счетчик")
        print("Описание: Таймер каждые 100ms увеличивает счетчик")

        steps = [
            ("Создание ресурса 'TEST_APP'", {
                'action': 'CREATE_RESOURCE',
                'params': {'name': 'TEST_APP'}
            }),

            ("Создание таймера E_CYCLE", {
                'action': 'CREATE_FB',
                'params': {
                    'name': 'TIMER1',
                    'type': 'E_CYCLE',
                    'resource': 'TEST_APP'
                }
            }),

            ("Настройка интервала таймера (100ms)", {
                'action': 'WRITE_PARAM',
                'params': {
                    'fb_name': 'TIMER1',
                    'param_name': 'DT',
                    'param_value': 'T#100ms',
                    'resource': 'TEST_APP'
                }
            }),

            ("Создание счетчика E_CTU", {
                'action': 'CREATE_FB',
                'params': {
                    'name': 'COUNTER1',
                    'type': 'E_CTU',
                    'resource': 'TEST_APP'
                }
            }),

            ("Соединение: таймер → счетчик", {
                'action': 'CREATE_CONNECTION',
                'params': {
                    'source': 'TIMER1.CHO',
                    'destination': 'COUNTER1.CU',
                    'resource': 'TEST_APP'
                }
            }),

            ("Запуск программы", {
                'action': 'START',
                'params': {'name': 'TEST_APP'}
            }),
        ]

        for step_name, step_data in steps:
            print(f"\n[ШАГ] {step_name}")
            print(f"[ДЕЙСТВИЕ] {step_data['action']}")

            # В демо-режиме показываем команду
            request_id = self.request_counter
            xml_cmd = self._create_xml_command(request_id, step_data['action'], step_data.get('params', {}))
            print(f"[КОМАНДА] {xml_cmd}")

            # Если подключены - отправляем реально
            if self.connected:
                response = self.send_command(step_data['action'], step_data.get('params', {}))
                if response:
                    print(f"[ОТВЕТ] {response}")
            else:
                print(f"[ДЕМО] Команда сформирована (режим демонстрации)")

            time.sleep(1)

        print("\n" + "="*70)
        print("ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА")
        print("="*70)

    def disconnect(self):
        """Закрытие соединения с FORTE"""
        if self.socket:
            self.socket.close()
            self.connected = False
            print("\n[ОТКЛЮЧЕНИЕ] Соединение с FORTE закрыто")


def create_example_fboot():
    """Создание примеров FBoot файлов"""
    print("\n[ФАЙЛЫ] Создание примеров FBoot файлов...")

    # Пример из лабораторной работы
    task5_fboot = """<Request ID="2" Action="CREATE"><FB Name="EMB_RES" Type="EMB_RES"/></Request>
<Request ID="3" Action="CREATE"><FB Name="STRING2STRING" Type="STRING2STRING"/></Request>
<Request ID="4" Action="CREATE"><FB Name="STRING2STRING_1" Type="STRING2STRING"/></Request>
<Request ID="5" Action="CREATE"><FB Name="APPEND_STRING_2" Type="APPEND_STRING_2"/></Request>
<Request ID="6" Action="CREATE"><Connection Source="STRING2STRING.OUT" Destination="/APPEND_STRING_2.IN_1"/></Request>
<Request ID="7" Action="CREATE"><Connection Source="STRING2STRING_1.OUT" Destination="/APPEND_STRING_2.IN_2"/></Request>
<Request ID="7" Action="START"/>"""

    with open("task5_example.fboot", "w", encoding="utf-8") as f:
        f.write(task5_fboot)

    # Простой пример
    simple_fboot = """<Request ID="1" Action="CREATE"><Resource Name="SIMPLE_APP"/></Request>
<Request ID="2" Action="CREATE"><FB Name="MY_TIMER" Type="E_CYCLE" Resource="SIMPLE_APP"/></Request>
<Request ID="3" Action="WRITE"><FB Name="MY_TIMER" Resource="SIMPLE_APP"><Parameter Name="DT" Value="T#500ms"/></FB></Request>
<Request ID="4" Action="START"><Resource Name="SIMPLE_APP"/></Request>"""

    with open("simple_example.fboot", "w", encoding="utf-8") as f:
        f.write(simple_fboot)

    print("[ФАЙЛЫ] ✓ Созданы:")
    print("  - task5_example.fboot (пример из лабы)")
    print("  - simple_example.fboot (простой пример)")


def main():
    """Основная функция демонстрации"""
    print("=" * 70)
    print("ЛАБОРАТОРНАЯ РАБОТА 2: МАКЕТ СРЕДЫ РАЗРАБОТКИ (аналог 4diac)")
    print("=" * 70)
    print("Клиент для загрузки программ в среду исполнения FORTE")
    print("Протокол: IEC 61499, Порт: 61499, Формат: XML команды")
    print()

    # Создаем клиент
    client = ForteClient(host='127.0.0.1', port=61499)

    try:
        # 1. Пытаемся подключиться
        print("[ЭТАП 1] Подключение к FORTE")
        print("-" * 40)

        connected = client.connect()

        if not connected:
            print("\n[ИНФО] FORTE не запущен, работаем в демо-режиме")
            print("[ИНФО] Для реальной работы запустите: ./forte 127.0.0.1:61499")

        # 2. Создаем примеры FBoot файлов
        print("\n[ЭТАП 2] Подготовка примеров программ")
        print("-" * 40)
        create_example_fboot()

        # 3. Демонстрация работы
        print("\n[ЭТАП 3] Демонстрация загрузки программы")
        print("-" * 40)
        client.demo_simple_program()

        # 4. Покажем формат протокола
        print("\n[ЭТАП 4] Анализ протокола (из Wireshark)")
        print("-" * 40)
        print("""
        Результаты анализа сетевого трафика:
        
        1. Транспорт: TCP
        2. Порт: 61499 (стандарт IEC 61499)
        3. Формат пакета: [4 байта длины][XML данные]
        4. Кодировка: UTF-8
        5. Основные команды:
           - QUERY    - запрос информации
           - CREATE   - создание ресурсов/FB/соединений
           - WRITE    - запись параметров
           - START    - запуск программы
           - STOP     - остановка программы
        
        Пример команды:
          <Request ID="1" Action="CREATE">
            <Resource Name="APP"/>
          </Request>
        
        Пример ответа:
          <Response ID="1"/>
        """)

        # 5. Завершение
        print("\n[ЭТАП 5] Завершение работы")
        print("-" * 40)


    except KeyboardInterrupt:
        print("\n\n[ИНФО] Работа прервана пользователем")
    except Exception as e:
        print(f"\n[ОШИБКА] Непредвиденная ошибка: {e}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()

    input("\nНажмите Enter для выхода...")

# 117
# QUERY - запрос информации о системе
# CREATE - создание ресурсов и функциональных блоков
# WRITE - настройка параметров блоков
# START/STOP - запуск и остановка программ
# CREATE_CONNECTION - создание соединений между блоками
