import groovy.json.JsonOutput

library(
    identifier: 'JenkinsPythonHelperLibrary@2024.12.0',
    retriever: modernSCM(
        [
            $class: 'GitSCMSource',
            remote: 'https://github.com/UIUCLibrary/JenkinsPythonHelperLibrary.git',
        ]
    )
)

def getSupportedPythonVersions(){
    return ['3.10', '3.11', '3.12', '3.13', '3.14']
}

def createWindowUVConfig(){
    return powershell(label: 'Setting up uv.toml config file', script: 'ci/jenkins/scripts/new-uv-global-config.ps1 $env:UV_INDEX_URL $env:UV_EXTRA_INDEX_URL', returnStdout: true).trim()
}

def createUnixUvConfig(){
    return sh(label: 'Setting up uv.toml config file', script: 'sh ci/jenkins/scripts/create_uv_config.sh $UV_INDEX_URL $UV_EXTRA_INDEX_URL', returnStdout: true).trim()
}

def testWindowsPackage(entry, params){
    node('windows && docker'){
        checkout scm
        try{
            unstash 'PYTHON_PACKAGES'
            docker.image('python').inside(
                "--label=purpose=ci --label \"JOB_NAME=\$JOB_NAME\" --label \"absoluteUrl=${currentBuild.absoluteUrl}\" --label \"BUILD_NUMBER=${currentBuild.number}\" " + \
                '-e UV_CACHE_DIR=C:\\Users\\ContainerUser\\Documents\\cache\\uvcache ' +
                '--mount type=volume,source=uv_python_cache_dir,target=C:\\Users\\ContainerUser\\Documents\\cache\\uvcache ' +
                '-e UV_PYTHON_CACHE_DIR=C:\\Users\\ContainerUser\\Documents\\cache\\uvpython_cache ' +
                '--mount type=volume,source=pipcache,target=C:\\Users\\ContainerUser\\Documents\\cache\\uvpython_cache ' +
                '-e UV_TOOL_DIR=C:\\Users\\ContainerUser\\Documents\\cache\\uvtools ' +
                '--mount type=volume,source=uv_cache_dir,target=C:\\Users\\ContainerUser\\Documents\\cache\\uvtools'
            ){
                bat(
                    label: 'Install uv',
                    script: '''python -m venv venv
                               .\\venv\\Scripts\\pip install --disable-pip-version-check uv
                               .\\venv\\Scripts\\uv python update-shell
                            '''
                )
                withEnv([
                    "UV_CONFIG_FILE=${createWindowUVConfig()}",
                    "TOX_UV_PATH=${WORKSPACE}/venv/Scripts/uv.exe"
                ]){
                    bat ".\\venv\\Scripts\\uv python install cpython-${entry.PYTHON_VERSION}"
                    script{
                        def packages = findFiles(glob: entry.PACKAGE_TYPE == 'wheel' ? 'dist/*.whl' : 'dist/*.tar.gz')
                        for (int i = 0; i < packages.length; i++) {
                            def attempt = 0
                            retry(2){
                                withEnv([(attempt == 0) ? 'UV_OFFLINE=1' : 'UV_OFFLINE=0']){
                                    attempt += 1
                                    bat(
                                        label: "Testing with tox: ${(attempt == 1) ? 'Offline' : 'Online'}",
                                        script: ".\\venv\\Scripts\\uv run --only-group=tox-uv --frozen tox --installpkg ${packages[i].path} -e py${entry.PYTHON_VERSION.replace('.', '')}"
                                    )
                                }
                            }
                        }
                    }
                }
            }
        } finally{
            bat(label: 'Cleaning up', script: "${tool(name: 'Default', type: 'git')} clean -dfx")
        }
    }
}

def testMacOSPackage(entry, params){
    node("macos && ${entry.ARCHITECTURE}"){
        checkout scm
        try{
            unstash 'PYTHON_PACKAGES'
            sh """python3 -m venv venv
                  ./venv/bin/pip install --disable-pip-version-check uv
                  uv python install cpython-${entry.PYTHON_VERSION}
               """
            withEnv(["TOX_UV_PATH=${WORKSPACE}/venv/bin/uv"]){
                def packages = findFiles(glob: entry.PACKAGE_TYPE == 'wheel' ? 'dist/*.whl' : 'dist/*.tar.gz')
                for (int i = 0; i < packages.length; i++) {
                    def attempt = 0
                    retry(2){
                        attempt += 1
                        withEnv([(attempt == 1) ? 'UV_OFFLINE=1' : 'UV_OFFLINE=0']){
                            sh(
                                label: "Testing with tox: ${(attempt == 1) ? 'Offline' : 'Online'}",
                                script: "./venv/bin/uv run --frozen --only-group=tox-uv tox --installpkg ${packages[i].path} -e py${entry.PYTHON_VERSION.replace('.', '')}"
                            )
                        }
                    }
                }
           }
        } finally{
            sh(label: 'Cleaning up', script: "${tool(name: 'Default', type: 'git')} clean -dfx")
        }
    }
}


def testPackage(entry, params){
    switch(entry.OS){
        case 'windows':
            testWindowsPackage(entry, params)
            break
        case 'macos':
            testMacOSPackage(entry, params)
            break
        default:
           error "Unable to test package due to unknown OS: ${entry.OS}"
    }
}

pipeline {
    agent none
    parameters{
        booleanParam(name: 'RUN_CHECKS', defaultValue: true, description: 'Run checks on code')
        booleanParam(name: 'TEST_RUN_TOX', defaultValue: false, description: 'Run Tox Tests')
        booleanParam(name: 'BUILD_PACKAGES', defaultValue: false, description: 'Build Packages')
        booleanParam(name: 'INCLUDE_MACOS-ARM64', defaultValue: false, description: 'Include ARM(m1) architecture for Mac')
        booleanParam(name: 'INCLUDE_MACOS-X86_64', defaultValue: false, description: 'Include x86_64 architecture for Mac')
        booleanParam(name: 'INCLUDE_WINDOWS-X86_64', defaultValue: true, description: 'Include x86_64 architecture for Windows')
        booleanParam(name: 'TEST_PACKAGES', defaultValue: true, description: 'Test Python packages by installing them and running tests on the installed package')
        booleanParam(name: 'CREATE_GITHUB_RELEASE', defaultValue: false, description: 'Deploy to Github Release. Requires the current commit to be tagged. Note: This is experimental')
    }
    options {
        durabilityHint 'PERFORMANCE_OPTIMIZED'
        preserveStashes()
    }
    stages {
        stage('Testing'){
            stages{
                stage('Build and Test'){
                    when{
                        equals expected: true, actual: params.RUN_CHECKS
                        beforeAgent true
                    }
                    environment{
                        PIP_CACHE_DIR='/tmp/pipcache'
                        UV_TOOL_DIR='/tmp/uvtools'
                        UV_PYTHON_CACHE_DIR='/tmp/uvpython'
                        UV_CACHE_DIR='/tmp/uvcache'
                    }
                    agent {
                        docker{
                            image 'ghcr.io/astral-sh/uv:debian'
                            label 'docker && linux && x86_64'
                            args "--label=purpose=ci --label \"JOB_NAME=\$JOB_NAME\" --label \"absoluteUrl=${currentBuild.absoluteUrl}\" --label \"BUILD_NUMBER=${currentBuild.number}\" --mount source=speedwagon_scripts_cache,target=/tmp --tmpfs /.config:exec --tmpfs /.tree-sitter:exec"
                        }
                    }
                    stages{
                        stage('Setup CI Environment'){
                            steps{
                                sh(
                                    label: 'Create virtual environment with packaging in development mode',
                                    script: 'uv sync --frozen --group ci'
                               )
                            }
                        }
                        stage('Run Tests'){
                            parallel {
                                stage('PyTest'){
                                    steps{
                                        sh(
                                            script: 'uv run coverage run --parallel-mode --source=package_speedwagon -m pytest --junitxml=./reports/tests/pytest/pytest-junit.xml'
                                        )
                                    }
                                    post {
                                        always {
                                            junit(allowEmptyResults: true, testResults: 'reports/tests/pytest/pytest-junit.xml')
                                        }
                                    }
                                }
                                stage('Audit uv.lock File'){
                                    options{
                                        timeout(5)
                                    }
                                    steps{
                                        catchError(buildResult: 'UNSTABLE', message: 'uv audit found issues', stageResult: 'UNSTABLE') {
                                            sh 'uv audit'
                                        }
                                    }
                                }
                                stage('Task Scanner'){
                                    steps{
                                        recordIssues(tools: [taskScanner(highTags: 'FIXME', includePattern: 'package_speedwagon/**/*.py', normalTags: 'TODO')])
                                    }
                                }
                                stage('Ruff') {
                                    steps{
                                        catchError(buildResult: 'SUCCESS', message: 'Ruff found issues', stageResult: 'UNSTABLE') {
                                            sh(
                                             label: 'Running Ruff',
                                             script: '''uv run ruff check --config=pyproject.toml -o reports/ruffoutput.txt --output-format pylint --exit-zero
                                                        uv run ruff check --config=pyproject.toml -o reports/ruffoutput.json --output-format json
                                                     '''
                                             )
                                        }
                                    }
                                    post{
                                        always{
                                            recordIssues(tools: [pyLint(pattern: 'reports/ruffoutput.txt', name: 'Ruff')])
                                        }
                                    }
                                }
                                stage('MyPy'){
                                    steps{
                                        catchError(buildResult: 'SUCCESS', message: 'MyPy found issues', stageResult: 'UNSTABLE') {
                                            tee('logs/mypy.log'){
                                                sh(label: 'Running MyPy',
                                                   script: 'uv run mypy -p package_speedwagon --html-report reports/mypy/html'
                                                )
                                            }
                                        }
                                    }
                                    post {
                                        always {
                                            recordIssues(tools: [myPy(pattern: 'logs/mypy.log')])
                                            publishHTML([allowMissing: true, alwaysLinkToLastBuild: false, keepAll: false, reportDir: 'reports/mypy/html/', reportFiles: 'index.html', reportName: 'MyPy HTML Report', reportTitles: ''])
                                        }
                                    }
                                }
                            }
                            post{
                                always{
                                    sh '''uv run coverage combine
                                          uv run coverage xml -o reports/coverage.xml
                                          uv run coverage html -d reports/coverage
                                       '''
                                    recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'reports/coverage.xml']])
                                }
                            }
                        }
                    }
                }
                stage('Tox'){
                    when {
                       equals expected: true, actual: params.TEST_RUN_TOX
                    }
                    parallel{
                        stage('macOS'){
                            when{
                                expression {return nodesByLabel('macos').size() > 0}
                            }
                            steps{
                                script{
                                    def envs = []
                                    node('macos'){
                                        checkout scm
                                        try{
                                            sh '''python3 -m venv uv
                                                  ./uv/bin/pip install --disable-pip-version-check uv
                                                '''
                                            withEnv(["UV_CONFIG_FILE=${createUnixUvConfig()}"]){
                                                envs = sh(
                                                    label: 'Get tox environments',
                                                    script: './uv/bin/uv run --quiet --frozen --isolated --only-group=tox tox list -d --no-desc',
                                                    returnStdout: true,
                                                ).trim().split('\n')
                                            }
                                        } finally{
                                            sh(label: 'Cleaning up', script: "${tool(name: 'Default', type: 'git')} clean -dfx")
                                        }
                                    }
                                    parallel(
                                        envs.collectEntries{toxEnv ->
                                            def version = toxEnv.replaceAll(/py(\d)(\d+)/, '$1.$2')
                                            [
                                                "Tox Environment: ${toxEnv}",
                                                {
                                                    node('macos && python3'){
                                                        timeout(30){
                                                            checkout scm
                                                            try{
                                                                sh(
                                                                    label: 'Install uv',
                                                                    script: """python3 -m venv uv
                                                                               uv/bin/pip install --disable-pip-version-check uv
                                                                               uv/bin/uv python install cpython-${version}
                                                                            """
                                                                )
                                                                withEnv([
                                                                    "UV_CONFIG_FILE=${createUnixUvConfig()}",
                                                                    "TOX_UV_PATH=${WORKSPACE}/uv/bin/uv"
                                                                ]){
                                                                    sh( label: 'Running Tox',
                                                                        script: "uv run --frozen --only-group=tox-uv --isolated tox run --runner uv-venv-lock-runner -e ${toxEnv} -vv"
                                                                        )
                                                                    }
                                                            } finally{
                                                                sh(label: 'Cleaning up', script: "${tool(name: 'Default', type: 'git')} clean -dfx")
                                                            }
                                                        }
                                                    }
                                                }
                                            ]
                                        }
                                    )
                                }
                            }
                        }
                        stage('Windows'){
                            when{
                                expression {return nodesByLabel('windows && docker && x86').size() > 0}
                            }
                            environment{
                                PIP_CACHE_DIR='C:\\Users\\ContainerUser\\Documents\\cache\\pipcache'
                                UV_TOOL_DIR='C:\\Users\\ContainerUser\\Documents\\cache\\uvtools'
                                UV_PYTHON_CACHE_DIR='C:\\Users\\ContainerUser\\Documents\\cache\\uvpython'
                                UV_CACHE_DIR='C:\\Users\\ContainerUser\\Documents\\cache\\uvcache'
                            }
                            steps{
                                script{
                                    def envs = []
                                    node('docker && windows'){
                                        checkout scm
                                        try{
                                            docker.image('python').inside(
                                                "--label=purpose=ci --label \"JOB_NAME=\$JOB_NAME\" --label \"absoluteUrl=${currentBuild.absoluteUrl}\" --label \"BUILD_NUMBER=${currentBuild.number}\" " + \
                                                "\
                                                --mount type=volume,source=uv_python_cache_dir,target=${env.UV_PYTHON_CACHE_DIR} \
                                                --mount type=volume,source=pipcache,target=${env.PIP_CACHE_DIR} \
                                                --mount type=volume,source=uv_cache_dir,target=${env.UV_CACHE_DIR}\
                                                "
                                            ){
                                                bat(label: 'Install uv', script: 'python -m venv venv && venv\\Scripts\\pip install --disable-pip-version-check uv')
                                                withEnv(["UV_CONFIG_FILE=${createWindowUVConfig()}"]){
                                                    envs = bat(
                                                        label: 'Get tox environments',
                                                        script: '@.\\venv\\Scripts\\uv run --quiet --only-group=tox --frozen tox list -d --no-desc',
                                                        returnStdout: true,
                                                    ).trim().split('\r\n')
                                                }
                                            }
                                        } finally{
                                            bat(label: 'Cleaning up', script: "${tool(name: 'Default', type: 'git')} clean -dfx")
                                        }
                                    }
                                    parallel(
                                        envs.collectEntries{toxEnv ->
                                            def version = toxEnv.replaceAll(/py(\d)(\d+)/, '$1.$2')
                                            [
                                                "Tox Environment: ${toxEnv}",
                                                {
                                                    node('docker && windows'){
                                                        timeout(30){
                                                            checkout scm
                                                            retry(3){
                                                                try{
                                                                    docker.image('python')
                                                                        .inside(
                                                                            "--label=purpose=ci --label \"JOB_NAME=\$JOB_NAME\" --label \"absoluteUrl=${currentBuild.absoluteUrl}\" --label \"BUILD_NUMBER=${currentBuild.number}\" " +
                                                                            "--mount type=volume,source=uv_python_cache_dir,target=${env.UV_PYTHON_CACHE_DIR} " +
                                                                            "--mount type=volume,source=pipcache,target=${env.PIP_CACHE_DIR} " +
                                                                            "--mount type=volume,source=uv_cache_dir,target=${env.UV_CACHE_DIR}"
                                                                        ){
                                                                        bat(label: 'Install uv',
                                                                            script: '''python -m venv uv && uv\\Scripts\\pip install --disable-pip-version-check uv
                                                                                       uv\\Scripts\\uv python update-shell
                                                                                    '''
                                                                        )
                                                                        withEnv(["UV_CONFIG_FILE=${createWindowUVConfig()}", "TOX_UV_PATH=${WORKSPACE}\\uv\\Scripts\\uv.exe"]){
                                                                            bat """uv\\Scripts\\uv python install cpython-${version}"""
                                                                            bat(label: 'Running Tox',
                                                                                script: "uv\\Scripts\\uv run --frozen --only-group=tox-uv --isolated tox run -e ${toxEnv} --runner uv-venv-lock-runner -vv"
                                                                            )
                                                                        }
                                                                    }
                                                                } finally{
                                                                    bat(label: 'Cleaning up', script: "${tool(name: 'Default', type: 'git')} clean -dfx")
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            ]
                                        }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
        stage('Python Packages'){
            when{
                equals expected: true, actual: params.BUILD_PACKAGES
                beforeAgent true
            }
            stages{
                stage('Packaging sdist and wheel'){
                    agent {
                        docker{
                            image 'ghcr.io/astral-sh/uv:debian'
                            label 'linux && docker'
                            args "--label=purpose=ci --label \"JOB_NAME=\$JOB_NAME\" --label \"absoluteUrl=${currentBuild.absoluteUrl}\" --label \"BUILD_NUMBER=${currentBuild.number}\" --mount source=python-tmp-uiucpreson_workflows,target=/tmp -e PIP_CACHE_DIR=/tmp/pipcache -e UV_CACHE_DIR=/tmp/uvcache"
                        }
                    }
                    options {
                        timeout(5)
                    }
                    steps{
                        sh(
                            label: 'Package',
                            script: 'uv build'
                        )
                        stash includes: 'dist/*.whl,dist/*.tar.gz,dist/*.zip', name: 'PYTHON_PACKAGES'
                    }
                    post{
                        cleanup{
                            cleanWs(
                                deleteDirs: true,
                                patterns: [
                                    [pattern: '**/__pycache__/', type: 'INCLUDE'],
                                    [pattern: 'venv/', type: 'INCLUDE'],
                                    [pattern: 'dist/', type: 'INCLUDE']
                                    ]
                                )
                        }
                    }
                }
                stage('Package Matrix'){
                    steps{
                        customMatrix(
                            axes: [
                                [
                                    name: 'PYTHON_VERSION',
                                    values: getSupportedPythonVersions()
                                ],
                                [
                                    name: 'OS',
                                    values: ['macos','windows']
                                ],
                                [
                                    name: 'ARCHITECTURE',
                                    values: ['x86_64', 'arm64']
                                ],
                                [
                                    name: 'PACKAGE_TYPE',
                                    values: ['wheel', 'sdist'],
                                ]
                            ],
                            excludes: [
                                [
                                    [
                                        name: 'OS',
                                        values: 'windows'
                                    ],
                                    [
                                        name: 'ARCHITECTURE',
                                        values: 'arm64',
                                    ]
                                ]
                            ],
                            when: {entry -> "INCLUDE_${entry.OS}-${entry.ARCHITECTURE}".toUpperCase() && params["INCLUDE_${entry.OS}-${entry.ARCHITECTURE}".toUpperCase()]},
                            stages: [
                                { entry ->
                                    stage('Test Package') {
                                        retry(1){
                                            testPackage(entry, params)
                                        }
                                    }
                                }
                            ]
                        )
                    }
                }
            }
        }
        stage('Deploy'){
            parallel{
                stage('GitHub Release'){
                    agent any
                    when{
                        beforeInput true
                        beforeAgent true
                        beforeOptions true
                        allOf{
                          equals expected: true, actual: params.CREATE_GITHUB_RELEASE
                          tag '*'
                        }
                    }
                    input {
                        message 'Create GitHub Release'
                        id 'GITHUB_DEPLOYMENT'
                        parameters {
                            credentials(
                                credentialType: 'org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl',
                                description: 'GitHub credential Id',
                                name: 'GITHUB_CREDENTIALS_ID',
                                required: true
                            )
                        }
                    }
                    options{
                        lock("${env.JOB_NAME}")
                    }
                    steps{
                        script {
                            def projectMetadata = readTOML( file: 'pyproject.toml')['project']
                            withCredentials([string(credentialsId: GITHUB_CREDENTIALS_ID, variable: 'GITHUB_TOKEN')]) {
                                def requestBody = JsonOutput.toJson([
                                    tag_name: env.BRANCH_NAME,
                                    name: "Version ${projectMetadata.version}",
                                    generate_release_notes: false,
                                    draft: false,
                                    prerelease: false
                                ])
                                def createReleaseResponse = httpRequest(
                                    httpMode: 'POST',
                                    contentType: 'APPLICATION_JSON',
                                    url: "https://api.github.com/repos/UIUCLibrary/speedwagon_scripts/releases",
                                    customHeaders: [
                                        [name: 'Authorization', value: "token ${GITHUB_TOKEN}"]
                                    ],
                                    requestBody: requestBody,
                                    validResponseCodes: '201' // Expect a 201 Created status code
                                    )
                                if (params.BUILD_PACKAGES){
                                    unstash 'PYTHON_PACKAGES'
                                    def releaseData = readJSON text: createReleaseResponse.content
                                    findFiles(glob: 'dist/*').each{
                                        def outputURL = "${releaseData.upload_url.replace('{?name,label}', '')}?name=${it.name}"
                                        def uploadResponse = httpRequest(
                                            url: "${outputURL}",
                                            httpMode: 'POST',
                                            uploadFile: it.path,
                                            customHeaders: [[name: 'Authorization', value: "token ${GITHUB_TOKEN}"]],
                                            wrapAsMultipart: false
                                        )
                                        if (uploadResponse.status >= 200 && uploadResponse.status < 300) {
                                            echo "File uploaded successfully to GitHub release."
                                        } else {
                                            error "Failed to upload file: ${uploadResponse.status} - ${uploadResponse.content}"
                                        }
                                    }
                                }
                            }
                        }
                    }
                    post{
                        cleanup{
                            script{
                                if(isUnix()){
                                    sh "${tool(name: 'Default', type: 'git')} clean -dfx"
                                } else {
                                    bat "${tool(name: 'Default', type: 'git')} clean -dfx"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}