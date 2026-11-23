from setuptools import find_packages, setup

package_name = 'fall_detection'

setup(
    name=package_name,
    version='0.2.0',
    packages=find_packages(exclude=['test', 'tests']),   # fall_detection, fall_core, ros
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/thresholds.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='song',
    maintainer_email='song@example.com',
    description='YOLO-pose based fall detection for Pinky Pro',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            # '실행 이름 = 파이썬모듈:함수'  ->  ros2 run fall_detection camera_node
            'camera_node = fall_detection.camera_node:main',
            'fall_node = fall_detection.fall_node:main',
            # STANDING 판정 + 낙상 후 경보 (fall_core 사용). 기존 fall_node는 그대로 둠
            'fall_core_node = ros.fall_node_adapter:main',
            # 터미널 실시간 대시보드 (비위험/주의/위험 + 관절 위치)
            'fall_monitor = ros.fall_monitor:main',
        ],
    },
)
