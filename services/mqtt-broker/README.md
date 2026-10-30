# mqtt-broker

Owner: Member B (Backend / IoT)

Eclipse Mosquitto 2 (`eclipse-mosquitto:2`). Config: [`config/mosquitto.conf`](config/mosquitto.conf).

| 항목 | 값 |
|------|----|
| Host port | `1883` (`MQTT_PORT`로 변경 가능) |
| Docker 내부 주소 | `mqtt-broker:1883` |
| ESP32 접속 주소 | **Docker를 실행하는 PC의 LAN IP**:1883 (`localhost`, `mqtt-broker` 사용 불가) |
| Persistence | `./data` → `/mosquitto/data` |
| Log | stdout (`docker compose logs mqtt-broker`) |

## 수동 확인

```bash
docker compose up -d mqtt-broker
docker compose exec mqtt-broker mosquitto_sub -t 'smart-media/#' -v
docker compose exec mqtt-broker mosquitto_pub -t smart-media/xiao-01/detection -m '{"hello":1}'
```

## 보안 (현재 데모 한계 및 개선 방향)

현재 `allow_anonymous true` — **로컬 LAN 데모 전용**이며 공용 인터넷에 노출하지 않습니다.

향후 개선:

1. `mosquitto_passwd -c /mosquitto/config/passwd <user>`로 계정 생성
2. `allow_anonymous false`, `password_file /mosquitto/config/passwd` 활성화
3. ACL로 device는 `smart-media/<device_id>/#` publish만, gateway는 subscribe만 허용
4. Firmware `config.h`, Gateway 환경변수(`MQTT_USERNAME`/`MQTT_PASSWORD`)에 credential 추가
5. 필요 시 TLS listener(8883) 추가
