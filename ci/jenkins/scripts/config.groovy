@NonCPS
def getExclusions(config){
    (config['supporting']['exclusions'] ?: []).collect{ exclusion ->
        return exclusion.collect{ component ->
            return ["name": component['name'], "values": component['values']]
        }
    }
}

def configData = [:]

def getConfig = { Map args = [:] ->
    def configID = args.configId ?: 'pipeline_config'
    if(!args.defaultConfigFile){
        error "Missing required parameter: defaultConfigFile"
    }
    def defaultConfigFile = args.defaultConfigFile
    if (configData.size() > 0) {
        echo "using cached configuration"
        return configData
    }
    echo "reading configuration"
    try{
        configFileProvider([configFile(fileId: configID, variable: 'config_file')]) {
            echo "Using configuration from: \"$configID\""
            configData = readJSON( file: config_file)
        }
    } catch (e){
        echo "Using default configuration in ${defaultConfigFile}. To override, create a new config file in Jenkins with id: \"${configID}\""
        configData = readJSON( file: defaultConfigFile)
    }
    configData['supporting']['exclusions'] = getExclusions(configData)
    return configData
}

return [
    getConfig: getConfig
]