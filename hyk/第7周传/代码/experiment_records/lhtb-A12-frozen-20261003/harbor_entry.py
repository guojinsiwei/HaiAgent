"""Keep shared verified base images when Harbor removes its own trial containers.

The bundled 0.7 runtime uses `compose down --rmi all`, which removes the tag
another parallel trial needs. Remove only that image-removal option; retain
container/volume cleanup and every official scoring/continuation behavior.
"""
from harbor.environments.docker.docker import DockerEnvironment

original = DockerEnvironment._run_docker_compose_command

async def preserve_images(self, command, *args, **kwargs):
    command = list(command)
    if command and command[0] == 'down' and '--rmi' in command:
        index = command.index('--rmi')
        if command[index:index + 2] != ['--rmi', 'all']:
            raise RuntimeError('Unexpected Harbor image removal policy')
        del command[index:index + 2]
    return await original(self, command, *args, **kwargs)

DockerEnvironment._run_docker_compose_command = preserve_images

if __name__ == '__main__':
    from harbor.cli.main import app
    app()
