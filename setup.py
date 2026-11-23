from setuptools import find_packages, setup

package_name = 'fall_detection'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='song',
    maintainer_email='song@example.com',
    description='YOLO-pose fall detection node',
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
        ],
    },
)
