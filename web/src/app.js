import React from 'react';
import './main.css';
import { updateComponentLibrary, checkForComponentLibraryUpdate } from './db'
import { ComponentOverview } from './componentTable'

class UpdateBar extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "updateAvailable": this.props.updateAvailable
    };
  }

  componentDidMount() {
    let checkStatus = () => {
      checkForComponentLibraryUpdate().then( updateAvailable => {
        this.setState({"updateAvailable": updateAvailable});
      });
    };

    checkStatus();
    this.timerID = setInterval(checkStatus, 60000);
  }

  componentWillUnmount() {
    clearInterval(this.timerID);
  }

  handleUpdateClick = (e) => {
    e.preventDefault();
    this.props.onTriggerUpdate();
  }

  render() {
    if (this.state.updateAvailable) {
      return <div className="flex flex-wrap w-full align-middle bg-orange-400 p-2">
                <p className="inline-block w-full md:w-1/2">There is an update of the component library available.</p>
                <button className="inline-block w-full md:w-1/2 bg-green-500 hover:bg-green-700 text-white font-bold py-2 px-4 rounded"
                        onClick={this.handleUpdateClick}>
                  Update the component library
                </button>
              </div>
    }
    else {
    return <div className="w-full bg-green-400 p-2">
              <p>The component database is up to-date. </p>
            </div>
    }
  }
}

class Updater extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "progress": {}
    };
  }

  componentDidMount() {
    updateComponentLibrary(
      (progress) => { this.setState({"progress": progress}); }
    ).then(() => { this.props.onFinish(); });
  }

  componentWillUnmount() {
  }

  listItems() {
    let items = []
    for (const [task, status] of Object.entries(this.state.progress)) {
      items.push(<li key={task}>{task}: {status}</li>);
    }
    return items;
  }

  render() {
    return <div className="w-full bg-green-400">
      <p>Update progress:</p>
      <ul className="list-disc">
        {this.listItems()}
      </ul>
    </div>
  }
}

function Container(props) {
  return <div className="container mx-auto px-2">{props.children}</div>
}

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      "updating": false
    };
  }

  onUpdateFinish = () => {
    // this.setState({"updating": false});
  }

  triggerUpdate = () => {
    this.setState({"updating": true});
  }

  render() {
    if (this.state.updating) {
      return <Container>
        <Updater onFinish={this.onUpdateFinish}/>
      </Container>
    }
    return (
        <Container>
          <UpdateBar onTriggerUpdate={this.triggerUpdate}/>
          <ComponentOverview/>
        </Container>
    );
  }
}

export default App;